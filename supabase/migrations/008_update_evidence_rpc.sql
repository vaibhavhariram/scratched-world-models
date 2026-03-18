-- Update RPC functions for multi-run score support
-- Adds new get_building_evidence_extended that handles multiple scores per building
-- Returns most recent score if run_id not specified, or score from specific run

CREATE OR REPLACE FUNCTION logistics.get_building_evidence_extended(
    p_building_id BIGINT,
    p_pipeline_run_id UUID DEFAULT NULL
)
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
        'score', CASE
            WHEN p_pipeline_run_id IS NOT NULL THEN (
                SELECT json_build_object(
                    'difficulty', bs.difficulty,
                    'stop_variance', bs.stop_variance,
                    'road_distance', bs.road_distance,
                    'entrance_count', bs.entrance_count,
                    'dwell_time', bs.dwell_time,
                    'sample_size', bs.sample_size,
                    'pipeline_run_id', bs.pipeline_run_id::text,
                    'computed_at', bs.computed_at
                )
                FROM logistics.building_scores bs
                WHERE bs.building_id = p_building_id AND bs.pipeline_run_id = p_pipeline_run_id
            )
            ELSE (
                SELECT json_build_object(
                    'difficulty', bs.difficulty,
                    'stop_variance', bs.stop_variance,
                    'road_distance', bs.road_distance,
                    'entrance_count', bs.entrance_count,
                    'dwell_time', bs.dwell_time,
                    'sample_size', bs.sample_size,
                    'pipeline_run_id', bs.pipeline_run_id::text,
                    'computed_at', bs.computed_at
                )
                FROM logistics.building_scores bs
                WHERE bs.building_id = p_building_id
                ORDER BY bs.computed_at DESC
                LIMIT 1
            )
        END,
        'validation_notes', COALESCE((
            SELECT json_agg(json_build_object(
                'id', v.id,
                'status', v.status,
                'note', v.note,
                'pipeline_run_id', v.pipeline_run_id::text,
                'created_at', v.created_at
            ) ORDER BY v.created_at DESC)
            FROM logistics.building_validation_notes v
            WHERE v.building_id = p_building_id
        ), '[]'::json),
        'rubric_scores', COALESCE((
            SELECT json_agg(json_build_object(
                'assignment_quality', brs.assignment_quality,
                'entrance_plausibility', brs.entrance_plausibility,
                'score_usefulness', brs.score_usefulness,
                'note', brs.note,
                'pipeline_run_id', brs.pipeline_run_id::text,
                'created_at', brs.created_at
            ) ORDER BY brs.created_at DESC)
            FROM logistics.building_rubric_scores brs
            WHERE brs.building_id = p_building_id
        ), '[]'::json)
    );
$$ LANGUAGE sql STABLE;
