-- Buildings from OpenStreetMap
CREATE TABLE logistics.buildings (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    osm_id          BIGINT UNIQUE NOT NULL,
    name            TEXT,
    address         TEXT,
    building_type   TEXT,
    footprint       GEOMETRY(POLYGON, 4326) NOT NULL,
    centroid        GEOMETRY(POINT, 4326) GENERATED ALWAYS AS (ST_Centroid(footprint)) STORED,
    area_sqm        DOUBLE PRECISION,
    perimeter_m     DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Raw taxi pickup/dropoff events filtered to Manhattan
CREATE TABLE logistics.stop_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL CHECK (event_type IN ('pickup', 'dropoff')),
    location        GEOMETRY(POINT, 4326) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    dwell_seconds   INTEGER,
    passenger_count SMALLINT,
    source_dataset  TEXT DEFAULT 'nyc_tlc',
    batch_id        UUID,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Junction: each stop assigned to its nearest building within threshold
CREATE TABLE logistics.building_stop_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id     BIGINT NOT NULL REFERENCES logistics.buildings(id),
    stop_event_id   BIGINT NOT NULL REFERENCES logistics.stop_events(id),
    distance_m      DOUBLE PRECISION NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (building_id, stop_event_id)
);

-- Clustered stop points suggesting building entrance locations
CREATE TABLE logistics.entrance_candidates (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id     BIGINT NOT NULL REFERENCES logistics.buildings(id),
    location        GEOMETRY(POINT, 4326) NOT NULL,
    cluster_size    INTEGER NOT NULL,
    avg_dwell_sec   DOUBLE PRECISION,
    stddev_position DOUBLE PRECISION,
    confidence      DOUBLE PRECISION CHECK (confidence BETWEEN 0 AND 1),
    side            TEXT,
    snap_to_edge    GEOMETRY(POINT, 4326),
    pipeline_run_id UUID,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Composite delivery difficulty score per building
CREATE TABLE logistics.building_scores (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id     BIGINT UNIQUE NOT NULL REFERENCES logistics.buildings(id),
    difficulty      DOUBLE PRECISION CHECK (difficulty BETWEEN 0 AND 1),
    stop_variance   DOUBLE PRECISION,
    road_distance   DOUBLE PRECISION,
    entrance_count  DOUBLE PRECISION,
    dwell_time      DOUBLE PRECISION,
    sample_size     INTEGER NOT NULL,
    pipeline_run_id UUID,
    computed_at     TIMESTAMPTZ DEFAULT now()
);

-- Pipeline job tracking for idempotency and observability
CREATE TABLE logistics.pipeline_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        TEXT NOT NULL CHECK (job_type IN ('ingest', 'cluster', 'score')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    params          JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error           TEXT,
    stats           JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
