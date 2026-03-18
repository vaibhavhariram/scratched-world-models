-- Validation and parameter tuning tooling
-- Enables: golden building selection, rubric scoring, parameter sweeps, run comparison

-- A. Golden buildings: curated set for manual validation
CREATE TABLE logistics.golden_buildings (
    building_id  BIGINT NOT NULL REFERENCES logistics.buildings(id),
    reason       TEXT,
    added_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (building_id)
);

CREATE INDEX idx_golden_added_at ON logistics.golden_buildings (added_at);

-- B. Rubric scores: quantitative validation per building per run
-- Allows raters to score assignment quality, entrance plausibility, and score usefulness
CREATE TABLE logistics.building_rubric_scores (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id             BIGINT NOT NULL REFERENCES logistics.buildings(id),
    pipeline_run_id         UUID NOT NULL,
    assignment_quality      SMALLINT NOT NULL CHECK (assignment_quality BETWEEN 0 AND 3),
    entrance_plausibility   SMALLINT NOT NULL CHECK (entrance_plausibility BETWEEN 0 AND 3),
    score_usefulness        SMALLINT NOT NULL CHECK (score_usefulness BETWEEN 0 AND 3),
    note                    TEXT,
    created_at              TIMESTAMPTZ DEFAULT now(),
    UNIQUE (building_id, pipeline_run_id)
);

CREATE INDEX idx_rubric_run ON logistics.building_rubric_scores (pipeline_run_id);
CREATE INDEX idx_rubric_building ON logistics.building_rubric_scores (building_id);

-- C. Fix building_scores to support multiple runs per building (for sweeps)
-- Previously had UNIQUE (building_id), now allows (building_id, pipeline_run_id) pairs
ALTER TABLE logistics.building_scores DROP CONSTRAINT building_scores_building_id_key;
ALTER TABLE logistics.building_scores ADD CONSTRAINT building_scores_building_run_unique
    UNIQUE (building_id, pipeline_run_id);

-- D. Add 'sweep' job type for parameter sweep runs
ALTER TABLE logistics.pipeline_jobs DROP CONSTRAINT pipeline_jobs_job_type_check;
ALTER TABLE logistics.pipeline_jobs ADD CONSTRAINT pipeline_jobs_job_type_check
    CHECK (job_type IN ('ingest', 'assign', 'cluster', 'score', 'sweep'));

-- E. Update RPC to handle multiple scores per building
-- Returns the most recent score (by computed_at DESC) for a building
-- Also includes rubric scores if they exist
CREATE OR REPLACE FUNCTION logistics.get_building_evidence_extended(p_building_id BIGINT, p_pipeline_run_id UUID DEFAULT NULL)
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
