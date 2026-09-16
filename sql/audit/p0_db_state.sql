-- P0.3 — database state audit (ROADMAP.md §2, P0 item 3). READ ONLY: every statement is a SELECT.
-- Run with `psql -f` against DATABASE_URL_RO: each statement is sent separately, so one failure does
-- not abort the rest. In the Supabase SQL editor run ONE SECTION AT A TIME — a pasted whole file
-- returns only the LAST statement's result and any error aborts the whole batch.
-- Migration state (is 009 applied?) is in the companion file sql/audit/p0_migration_state.sql.
-- SCHEMA IS `logistics`, NOT `public` (002:1) — a role granted only on `public` fails every query
-- here with "permission denied for schema logistics". If S3 errors with `function st_xmin does not
-- exist`, uncomment the next line (session-local, writes nothing, only non-SELECT in this file):
-- SET search_path = logistics, public, extensions;

-- ============================== S1 — INVENTORY ==============================
-- S1.1 Tables. No migration declares PARTITION BY, so `kind` should read 'table' throughout.
-- est_rows = -1 means the relation has never been vacuumed or analyzed (PG14+), NOT that it is
-- empty — S1.2 is the exact count either way.
SELECT c.relname AS table_name, c.reltuples::bigint AS est_rows,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'PARTITIONED' END AS kind
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'logistics' AND c.relkind IN ('r','p')
ORDER BY pg_total_relation_size(c.oid) DESC;

-- S1.2 Exact counts (reltuples above is only an estimate).
SELECT 'buildings' AS table_name, count(*) AS exact_rows FROM logistics.buildings
UNION ALL SELECT 'stop_events',          count(*) FROM logistics.stop_events
UNION ALL SELECT 'building_stop_events', count(*) FROM logistics.building_stop_events
UNION ALL SELECT 'entrance_candidates',  count(*) FROM logistics.entrance_candidates
UNION ALL SELECT 'building_scores',      count(*) FROM logistics.building_scores
UNION ALL SELECT 'pipeline_jobs',        count(*) FROM logistics.pipeline_jobs
ORDER BY exact_rows DESC;

-- S1.3 Indexes. P0.4-relevant: building_scores has no index on computed_at (004:15-16). The only
-- pipeline_run_id coverage is the TRAILING column of UNIQUE (building_id, pipeline_run_id) added at
-- 007:34-35, which a DISTINCT ON (building_id) ORDER BY building_id, computed_at DESC cannot use.
SELECT t.relname AS table_name, i.relname AS index_name, ix.indisunique AS is_unique,
       pg_size_pretty(pg_relation_size(i.oid)) AS size
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'logistics' ORDER BY t.relname, i.relname;

-- S1.4 PostGIS version. SUBSTITUTION: reads the catalog instead of postgis_full_version() so it
-- works regardless of search_path, but loses the GEOS/PROJ/GDAL versions and the library-vs-script
-- skew warning. For those, run extensions.postgis_full_version() using the installed_in value below.
SELECT e.extname, e.extversion, n.nspname AS installed_in
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace ORDER BY e.extname;

-- =========================== S2 — PIPELINE RUN STATE ===========================
-- NOTE: building_scores timestamps are `computed_at` (003:66), not `created_at`.
-- S2.1 Run cardinality and unattributed rows.
SELECT count(*) AS score_rows, count(DISTINCT pipeline_run_id) AS distinct_runs,
       count(*) FILTER (WHERE pipeline_run_id IS NULL) AS rows_with_null_run
FROM logistics.building_scores;

-- S2.2 Rows and time window per run.
SELECT pipeline_run_id::text AS run_id, count(*) AS n_rows,
       count(DISTINCT building_id) AS n_buildings,
       min(computed_at) AS first_computed, max(computed_at) AS last_computed
FROM logistics.building_scores GROUP BY 1 ORDER BY max(computed_at) DESC NULLS LAST;

-- S2.3 BLAST RADIUS of the multi-run read bug; the number that sizes P0.4. get_building (005:23) is
-- an unbounded scalar subquery, raising "more than one row..." for any building with >1 ROW.
-- Rows and runs differ: pipeline_run_id is nullable (003:65) and UNIQUE is NULLS DISTINCT, so
-- several NULL-run rows for one building are legal. Both counts reported; they can disagree.
SELECT count(*) FILTER (WHERE n_rows > 1) AS buildings_with_multiple_rows,
       count(*) FILTER (WHERE n_runs > 1) AS buildings_in_multiple_runs
FROM (SELECT building_id, count(*) AS n_rows, count(DISTINCT pipeline_run_id) AS n_runs
      FROM logistics.building_scores GROUP BY building_id) x;

-- S2.4 Same for entrance_candidates, which has no uniqueness constraint at all (003:41-53).
SELECT count(*) AS total, count(DISTINCT pipeline_run_id) AS distinct_runs,
       count(*) FILTER (WHERE pipeline_run_id IS NULL) AS rows_with_null_run,
       (SELECT count(*) FROM (SELECT 1 FROM logistics.entrance_candidates
        GROUP BY building_id, pipeline_run_id) y) AS building_run_pairs
FROM logistics.entrance_candidates;

-- S2.5 Run ledger. job_tracker.py writes a row per invocation incl. failures — empty = never ran.
SELECT id::text AS run_id, job_type, status, created_at, started_at, completed_at,
       params->>'year' AS tlc_year, params->>'month' AS tlc_month,
       params->>'dry_run' AS dry_run, params->>'row_limit' AS row_limit, stats, error
FROM logistics.pipeline_jobs ORDER BY created_at;

-- ========================= S3 — REAL DATA VS FIXTURE =========================
-- S3.1 Temporal extent. ONE timestamp column (event_timestamp, 003:22) discriminated by
-- event_type (003:20) — no separate pickup/dropoff columns — so min/max is a grouping.
SELECT event_type, count(*) AS n, min(event_timestamp) AS earliest,
       max(event_timestamp) AS latest, count(DISTINCT event_timestamp::date) AS distinct_days
FROM logistics.stop_events GROUP BY event_type ORDER BY event_type;

-- S3.1b Table-wide distinct dates. stops.py emits a pickup AND a dropoff row per trip, so S3.1's
-- two date sets overlap and cannot be summed. This is the figure that reads as a fixture tell:
-- a real TLC month has ~28-31 distinct dates, a generated fixture typically has 1-2.
SELECT count(DISTINCT event_timestamp::date) AS distinct_days_all,
       min(event_timestamp) AS earliest_all, max(event_timestamp) AS latest_all
FROM logistics.stop_events;

-- S3.2 FLAGGED — NOT RUNNABLE AS SPECIFIED. No medallion, hack-licence or vendor column exists.
-- stop_events (003:17-28) is: id, source_id, event_type, location, event_timestamp, dwell_seconds,
-- passenger_count, source_dataset, batch_id, created_at. stops.py:88-93 persists only lat/lng,
-- timestamp, passenger_count, 'nyc_tlc' and batch_id — TLC vendor/licence fields are dropped at
-- ingest and NOT recoverable from this DB. Nearest provenance proxies:
SELECT source_dataset, count(*) AS n_rows, count(DISTINCT batch_id) AS n_batches,
       min(split_part(source_id,'-',1)) AS min_year, max(split_part(source_id,'-',1)) AS max_year
FROM logistics.stop_events GROUP BY source_dataset ORDER BY n_rows DESC;

-- S3.3 Coordinate envelope vs the NYC bounding box.
SELECT count(*) AS total,
       count(*) FILTER (WHERE NOT ST_Within(location,
           ST_MakeEnvelope(-74.26,40.49,-73.70,40.92,4326))) AS outside_nyc,
       round(100.0 * count(*) FILTER (WHERE NOT ST_Within(location,
           ST_MakeEnvelope(-74.26,40.49,-73.70,40.92,4326))) / NULLIF(count(*),0), 4) AS pct_outside,
       ST_XMin(ST_Extent(location)) AS min_lng, ST_YMin(ST_Extent(location)) AS min_lat,
       ST_XMax(ST_Extent(location)) AS max_lng, ST_YMax(ST_Extent(location)) AS max_lat
FROM logistics.stop_events;

-- S3.4 Exactly-duplicated coordinates — the fixture tell. Real TLC lat/lng is float-noisy.
SELECT count(*) AS repeated_coords, sum(n) AS rows_at_repeated_coords,
       max(n) AS max_rows_at_one_coord
FROM (SELECT ST_AsBinary(location) AS g, count(*) AS n
      FROM logistics.stop_events GROUP BY 1 HAVING count(*) > 1) d;

-- ========================== S4 — DWELL-TIME FACTOR ==========================
-- S4.1 THE MEASURED NULL RATE — moves dwell removal off "UNTESTED — inherited" in DECISIONS.md.
-- workers/src/ingest/stops.py:93 writes the literal \N into the dwell_seconds column position
-- (COPY column order at workers/src/ingest/stops.py:99-100). Expect pct_null = 100.0000.
SELECT count(*) AS total_rows, count(dwell_seconds) AS non_null,
       count(*) - count(dwell_seconds) AS null_rows,
       round(100.0*(count(*)-count(dwell_seconds))/NULLIF(count(*),0),4) AS pct_null
FROM logistics.stop_events;

-- S4.2 Any non-null sample. Expect zero rows; a non-empty result falsifies the finding.
SELECT id, source_id, event_type, event_timestamp, dwell_seconds, batch_id
FROM logistics.stop_events WHERE dwell_seconds IS NOT NULL LIMIT 20;

-- S4.3 Downstream columns. avg_dwell_sec feeds workers/src/score/compute.py:159; dwell_time is the
-- sub-score (003:63). distinct_dwell_time_values = 1 with min = max = 0.5 confirms dwell is a
-- constant. distinct_road_distance_values is included because road_distance (003:61) is populated
-- from stop-to-footprint distance, not from any road — see compute.py:153 and stops.py:134.
SELECT count(*) AS candidates, count(avg_dwell_sec) AS avg_dwell_non_null,
       min(avg_dwell_sec) AS min_avg, max(avg_dwell_sec) AS max_avg
FROM logistics.entrance_candidates;
SELECT count(*) AS scores, count(DISTINCT dwell_time) AS distinct_dwell_time_values,
       min(dwell_time) AS min_v, max(dwell_time) AS max_v,
       count(DISTINCT road_distance) AS distinct_road_distance_values
FROM logistics.building_scores;
