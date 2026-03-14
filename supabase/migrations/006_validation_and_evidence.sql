-- Manual validation notes for QA review of clustering results
CREATE TABLE logistics.building_validation_notes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id     BIGINT NOT NULL REFERENCES logistics.buildings(id),
    pipeline_run_id UUID,
    status          TEXT NOT NULL CHECK (status IN (
                        'plausible',
                        'wrong_building',
                        'diffuse_cluster',
                        'good_candidate',
                        'needs_tuning'
                    )),
    note            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_validation_building ON logistics.building_validation_notes (building_id);
CREATE INDEX idx_validation_status ON logistics.building_validation_notes (status);


-- Evidence inspection: return a building's assigned stops as GeoJSON points
-- Used by the frontend debug panel to show raw stop data around a building
CREATE OR REPLACE FUNCTION logistics.get_building_evidence(p_building_id BIGINT)
RETURNS JSON AS $$
    SELECT json_build_object(
        'building', (SELECT logistics.get_building(p_building_id)),
        'stops', json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE((
                SELECT json_agg(json_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(s.location)::json,
                    'properties', json_build_object(
                        'id', s.id,
                        'event_type', s.event_type,
                        'event_timestamp', s.event_timestamp,
                        'dwell_seconds', s.dwell_seconds,
                        'distance_m', bse.distance_m,
                        'passenger_count', s.passenger_count
                    )
                ))
                FROM logistics.stop_events s
                JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
                WHERE bse.building_id = p_building_id
            ), '[]'::json)
        ),
        'stop_count', (
            SELECT COUNT(*)
            FROM logistics.building_stop_events
            WHERE building_id = p_building_id
        ),
        'validation_notes', COALESCE((
            SELECT json_agg(json_build_object(
                'id', v.id,
                'status', v.status,
                'note', v.note,
                'pipeline_run_id', v.pipeline_run_id,
                'created_at', v.created_at
            ) ORDER BY v.created_at DESC)
            FROM logistics.building_validation_notes v
            WHERE v.building_id = p_building_id
        ), '[]'::json)
    );
$$ LANGUAGE sql STABLE;
