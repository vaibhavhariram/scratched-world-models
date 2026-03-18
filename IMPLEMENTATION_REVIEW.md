# Logistics World Graph — Implementation Review

**Project**: Infer building entrance locations and delivery difficulty scores from taxi trajectory stop data.
**MVP Scope**: Manhattan using NYC Taxi dataset + OpenStreetMap building footprints.
**Status**: MVP complete with validation tooling phase 1.

---

## Executive Summary

| Component | Status | Coverage |
|-----------|--------|----------|
| **Database Schema** | ✅ Complete | 9 tables, 8 migrations, 16 indexes, 5 RPC functions |
| **Backend API** | ✅ Complete | 4 REST endpoints (buildings, entrances, evidence) |
| **Frontend Map** | ✅ Complete | deck.gl heatmap + scatterplot layers, EvidencePanel inspector |
| **Pipeline** | ✅ Complete | Ingest → Assign → Cluster → Score (5 stages) |
| **Job Tracking** | ✅ Complete | Idempotency + observability for all runs |
| **Validation Tooling** | ✅ Phase 1 | Golden buildings, sanity checks, rubric scoring, parameter sweeps, run comparison |
| **Tests** | ❌ None | Zero automated tests |
| **Auth** | ❌ None | All endpoints public (MVP acceptable) |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (Next.js 15 + React 19 + deck.gl 9)               │
│ • Map visualization (buildings, entrances, heatmap)        │
│ • EvidencePanel debug inspector                            │
│ • Real-time pan/zoom with bbox filtering                  │
└────────────────┬────────────────────────────────────────────┘
                 │ JSON (REST API)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ API LAYER (Next.js Route Handlers)                         │
│ • /api/buildings?bbox=... → GeoJSON FeatureCollection     │
│ • /api/entrances?bbox=... → GeoJSON FeatureCollection     │
│ • /api/buildings/:id → JSON building + score breakdown    │
│ • /api/buildings/:id/evidence → Full debug data           │
└────────────────┬────────────────────────────────────────────┘
                 │ SQL RPC calls
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ SUPABASE (Postgres + PostGIS)                               │
│ • 9 tables: buildings, stops, assignments, entrances,     │
│   scores, jobs, validation notes, golden set, rubric     │
│ • Spatial indexes on all geometry columns                 │
│ • 5 RPC functions for API + internal queries             │
└────────────────┬────────────────────────────────────────────┘
                 │ psycopg2
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ PYTHON WORKERS (CLI)                                        │
│ Stage 1: Ingest buildings (Overpass API)                  │
│ Stage 2: Ingest stops (NYC TLC) + Assign to buildings     │
│ Stage 3: DBSCAN clustering → entrance candidates          │
│ Stage 4: Difficulty scoring (4 sub-scores, normalized)    │
│ Validation: Golden buildings, sanity checks, sweeps       │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Core Tables

**1. `buildings`** — OpenStreetMap footprints
- `id` (BIGINT PK), `osm_id` (UNIQUE), `name`, `address`, `building_type`
- `footprint` (POLYGON 4326), `centroid` (POINT, computed)
- `area_sqm`, `perimeter_m`, timestamps

**2. `stop_events`** — NYC TLC taxi pickup/dropoff events (Manhattan-filtered)
- `id` (BIGINT PK), `source_id`, `event_type` ('pickup'|'dropoff')
- `location` (POINT 4326), `event_timestamp`, `dwell_seconds`, `passenger_count`
- `batch_id` (UUID from ingest job), `source_dataset`, timestamps

**3. `building_stop_events`** — Assignment junction (stop → nearest building)
- `id` (BIGINT PK), `building_id` (FK), `stop_event_id` (FK)
- `distance_m` (distance from stop to building)
- UNIQUE constraint ensures one assignment per stop

**4. `entrance_candidates`** — DBSCAN-inferred entrances (per pipeline run)
- `id` (BIGINT PK), `building_id` (FK), `location` (POINT 4326)
- `cluster_size`, `avg_dwell_sec`, `stddev_position`
- `confidence` (0-1: 0.6 × size + 0.4 × spread), `side` (north/south/east/west)
- `pipeline_run_id` (UUID), `snap_to_edge` (schema-only, not computed)

**5. `building_scores`** — Difficulty score per building per pipeline run
- `id` (BIGINT PK), `building_id` (FK), `pipeline_run_id` (UUID FK)
- `difficulty` (0-1 composite), `stop_variance` (0-1), `road_distance` (0-1)
- `entrance_count` (0-1), `dwell_time` (0-1), `sample_size` (int)
- **UNIQUE(building_id, pipeline_run_id)** — allows multi-run scores

**6. `pipeline_jobs`** — Job tracking for all pipeline runs
- `id` (UUID PK), `job_type` ('ingest'|'assign'|'cluster'|'score'|'sweep')
- `status` ('pending'|'running'|'completed'|'failed')
- `params` (JSONB: CLI args), `stats` (JSONB: metrics)
- `started_at`, `completed_at`, `error` (first 4000 chars), timestamps

**7. `building_validation_notes`** — Manual QA status labels
- `id` (BIGINT PK), `building_id` (FK), `pipeline_run_id` (UUID)
- `status` ('plausible'|'wrong_building'|'diffuse_cluster'|'good_candidate'|'needs_tuning')
- `note` (TEXT), timestamps

**8. `golden_buildings`** — Curated set for validation across sweeps
- `building_id` (BIGINT PK FK), `reason` (TEXT), `added_at`

**9. `building_rubric_scores`** — Quantitative validation (per building, per run)
- `id` (BIGINT PK), `building_id` (FK), `pipeline_run_id` (UUID FK)
- `assignment_quality` (0-3), `entrance_plausibility` (0-3), `score_usefulness` (0-3)
- `note` (TEXT), timestamps
- **UNIQUE(building_id, pipeline_run_id)**

### Indexes

- **Spatial (GIST)**: `buildings.footprint`, `buildings.centroid`, `stop_events.location`, `entrance_candidates.location`
- **B-Tree**: Foreign keys, timestamps, UUID fields for fast joins and time-based filtering

### RPC Functions

1. **`get_building(p_id BIGINT) → JSON`**
   - Single building with geometry, metadata, score, entrances

2. **`get_buildings_in_bbox(w, s, e, n, min_score=0, max_score=1, limit=500) → JSON`**
   - GeoJSON FeatureCollection of buildings in viewport

3. **`get_entrances_in_bbox(w, s, e, n, limit=1000) → JSON`**
   - GeoJSON FeatureCollection of entrance candidates

4. **`get_building_evidence(p_id BIGINT) → JSON`**
   - Full debug data: stops, validation notes, rubric scores

5. **`get_building_evidence_extended(p_id BIGINT, p_run_id UUID=NULL) → JSON`**
   - Same as above but supports querying by specific pipeline run

---

## API Endpoints

| Method | Path | Query Params | Returns | Purpose |
|--------|------|--------------|---------|---------|
| GET | `/api/buildings` | `bbox=w,s,e,n` (req), `min_score`, `max_score`, `limit=500` | GeoJSON FeatureCollection | Buildings in viewport, colored by difficulty |
| GET | `/api/buildings/:id` | (none) | JSON building object | Single building metadata + score + entrances |
| GET | `/api/buildings/:id/evidence` | (none) | JSON evidence object | Full debug data: stops, entrances, notes, rubric |
| GET | `/api/entrances` | `bbox=w,s,e,n` (req), `limit=1000` | GeoJSON FeatureCollection | Entrance candidates in viewport |

All endpoints:
- Return 400 on invalid params, 404 if building not found, 500 on DB error
- Call RPC functions directly from Supabase
- Use server-side Supabase client for security

---

## Frontend

### Tech Stack
- **Next.js 15** (App Router)
- **React 19** + TypeScript
- **deck.gl 9** (large-scale visualization)
- **Mapbox GL** (base map)
- **SWR 2** (data fetching, 2s dedup interval)
- **Tailwind CSS 4** (styling)

### Pages & Routes
- `/` — Home page with full-screen map (MapContainer)
- `/api/*` — 4 API routes calling Supabase RPCs

### Components

**MapContainer** (`web/src/components/map/MapContainer.tsx`)
- Central orchestrator: manages viewport state, fetches buildings/entrances
- Renders 3 deck.gl layers:
  1. **GeoJsonLayer** (buildings) — colored by difficulty (green → yellow → red)
  2. **ScatterplotLayer** (entrances) — sized by cluster_size, colored by confidence
  3. **HeatmapLayer** (optional) — difficulty heatmap at building centroids
- Click building → open EvidencePanel

**MapControls** (`web/src/components/map/MapControls.tsx`)
- Left sidebar: toggle heatmap/entrances, score range slider
- Shows current zoom level, loading spinner

**EvidencePanel** (`web/src/components/panels/EvidencePanel.tsx`)
- Right sidebar (opens on building click)
- Shows:
  - Building name, address, type, area
  - Difficulty score (0-1, color-coded)
  - Score breakdown: 4 sub-scores (each 0-1)
  - Sample size (number of assigned stops)
  - Entrance candidates: confidence %, side, cluster size, dwell time
  - Assigned stops (first 20): type, distance, timestamp
  - Validation notes: status, note, date

### Custom Hooks

**useMapData** — Fetch buildings + entrances in bbox; debounced on viewport change
**useBuilding** — Fetch single building (not used in MVP)
**useEvidence** — Fetch full evidence for debug panel

All use SWR with automatic deduplication and error handling.

### Visualization Details

- **Difficulty Coloring**: 0 (green, easy) → 0.5 (yellow, medium) → 1 (red, hard)
- **Confidence Coloring**: 0 (light blue, low) → 1 (deep blue, high)
- **Heatmap Opacity**: 0.6; only visible at zoom < 15
- **Entrance Visibility**: Only shown at zoom ≥ 16 (prevents clutter)
- **Performance**: Viewport → bbox conversion uses optimized math; map pan/zoom is smooth

---

## Python Workers Pipeline

### Stage 1: Ingest Buildings
```
Fetch OpenStreetMap building footprints (Overpass API)
→ Parse GeoJSON polygons
→ Validate geometries (shapely)
→ Compute area (UTM) and perimeter
→ INSERT buildings table (ON CONFLICT osm_id DO UPDATE)
Returns: { total_parsed, inserted, updated }
```

**Command**: `python -m src.main ingest-buildings [--dry-run] [--row-limit N]`

### Stage 2: Ingest Stops + Assign
```
Download NYC TLC yellow taxi .parquet for month
→ Extract pickup + dropoff events
→ Filter to Manhattan bbox
→ FOR EACH stop:
   ├─ Find nearest building within 50m (ST_DWithin)
   └─ INSERT building_stop_events
Returns: { stops_ingested, stops_assigned, unassigned_stops, assignment_rate }
```

**Commands**:
- `python -m src.main ingest-stops --year Y --month M [--dry-run] [--row-limit N]`
- `python -m src.main assign --batch-id UUID [--assignment-radius 50]`

### Stage 3: DBSCAN Clustering
```
FOR EACH building with ≥5 assigned stops:
  ├─ Fetch stop coordinates, transform to UTM
  ├─ Run DBSCAN(eps=5m, min_samples=3)
  ├─ FOR EACH cluster (skip noise):
  │   ├─ Compute centroid, stddev position
  │   ├─ Confidence = 0.6 × (size_score) + 0.4 × (spread_score)
  │   ├─ Determine side (north/south/east/west) relative to building
  │   └─ INSERT entrance_candidates
  └─ Mark building as processed (idempotent)
Returns: { eligible_buildings, clustered_buildings, entrance_candidates_created }
```

**Command**: `python -m src.main cluster [--eps 5.0] [--min-samples 3] [--building-id ID | --bbox W,S,E,N | --rerun-pipeline UUID] [--dry-run]`

### Stage 4: Difficulty Scoring
```
Compute global 5-95th percentile stats across all buildings
FOR EACH building with entrance candidates:
  ├─ Compute 4 sub-scores:
  │   1. stop_variance = STDDEV(X) + STDDEV(Y) in UTM
  │   2. road_distance = AVG(distance_m from assignment)
  │   3. entrance_count = COUNT(*) entrances this run
  │   4. dwell_time = AVG(avg_dwell_sec from entrances)
  ├─ Normalize each to [0,1] using global ranges
  ├─ Composite = weighted sum (0.25 each by default)
  └─ INSERT building_scores (ON CONFLICT building_id, pipeline_run_id)
Returns: { scored_buildings, difficulty_min, difficulty_max, difficulty_mean, difficulty_median }
```

**Command**: `python -m src.main score [--building-id ID | --bbox W,S,E,N | --rerun-pipeline UUID] [--dry-run]`

### Configuration & Parameters

| Parameter | Default | CLI Flag | Scope |
|-----------|---------|----------|-------|
| assignment_radius_m | 50m | `--assignment-radius` | assign |
| dbscan_eps_m | 5m | `--eps` | cluster |
| dbscan_min_samples | 3 | `--min-samples` | cluster |
| min_building_samples | 5 | `--min-building-samples` | cluster, score |
| row_limit | unlimited | `--row-limit` | ingest |
| dry_run | false | `--dry-run` | all |

---

## Validation Tooling (Phase 1)

### Purpose
Enable rapid experimentation: run small datasets, manually review results, test parameter combinations.

### Golden Buildings
Select a curated set (~20-30) for validation across all parameter sweeps.

**Commands**:
```bash
# Add buildings
python -m src.main golden-add --building-ids 101,204,305 --reason "diverse types"

# List with stop counts
python -m src.main golden-list

# Remove
python -m src.main golden-remove --building-ids 101
```

### Sanity Checks
Flag data quality issues before clustering.

**Checks**:
- Zero coordinates (0,0) or NULL location
- Duplicate stops (same location + timestamp)
- Tiny extent (<1m) → all stops at same point
- Huge extent (>200m) → misassigned or huge building

**Command**: `python -m src.main sanity-check [--building-id ID]`

### Rubric Scoring
Quantitative validation on 0-3 scales.

**Dimensions**:
- **Assignment Quality**: Do stops belong to the right building?
- **Entrance Plausibility**: Are inferred entrances on real building facades?
- **Score Usefulness**: Is the difficulty score directionally correct?

**Commands**:
```bash
# Single building
python -m src.main rubric --pipeline-run-id UUID --building-id ID \
    --assignment 2 --entrance 3 --score 1 --note "entrances good"

# Interactive batch (iterate golden buildings)
python -m src.main rubric-batch --pipeline-run-id UUID
# → Prompts for 3 scores per building, saves to DB
```

### Parameter Sweeps
Test multiple clustering parameter combinations in one run.

**Command**:
```bash
python -m src.main sweep --eps 3,5,7 --min-samples 2,3,5 --tag "march-tuning-v1"
```

Produces: 3 × 3 = 9 jobs, each with own UUID.

### Run Comparison
Compare sweep results side-by-side.

**Commands**:
```bash
# Specific runs
python -m src.main compare --run-ids UUID1,UUID2,UUID3

# All runs with tag
python -m src.main compare --tag "march-tuning-v1"
```

**Output**:
- Run metrics table (eps, min_samples, entrance count, avg confidence, avg difficulty)
- Golden buildings detail (entrances, confidence, difficulty, rubric per run)

---

## Typical Validation Workflow

1. **Ingest small dataset**: 1 month, current parameters
   ```bash
   python -m src.main ingest-stops --year 2015 --month 1 --row-limit 50000
   python -m src.main assign --batch-id <uuid>
   python -m src.main cluster
   python -m src.main score
   ```

2. **Select golden buildings**: Diverse buildings (apartments, offices, hotels, corners)
   ```bash
   python -m src.main golden-add --building-ids 101,204,305 --reason "mix"
   python -m src.main golden-list  # verify
   ```

3. **Run sanity checks**
   ```bash
   python -m src.main sanity-check
   ```

4. **Score golden buildings manually**
   ```bash
   python -m src.main rubric-batch --pipeline-run-id <uuid>
   ```

5. **Test parameter combinations**
   ```bash
   python -m src.main sweep --eps 3,5,7 --min-samples 2,3,5 --tag "v1"
   ```

6. **Compare results**
   ```bash
   python -m src.main compare --tag "v1"
   ```

7. **Lock baseline**: Use best parameters for production runs

---

## Known Limitations

### Not Implemented
- **Entrance snapping**: `snap_to_edge` column exists but snapping logic not implemented
- **Multi-run UI**: `get_building_evidence_extended()` RPC exists but frontend always shows most recent score
- **Validation notes creation**: No API to create/edit notes; schema only
- **Batch validation**: No command to bulk-add status labels
- **Historical comparison UI**: No map UI to compare building scores across runs
- **Export**: No CSV/GeoJSON export functionality
- **Authentication**: All endpoints public
- **Rate limiting**: No API rate limits

### Partial / Polish
- **Error UI**: Generic error messages; no user-friendly handling
- **Loading states**: Spinner present but no granular layer feedback
- **Empty states**: No explanatory messages when buildings lack entrances
- **Mobile responsiveness**: Not tested; controls may be off-screen
- **Dark mode only**: No light theme
- **Test coverage**: Zero automated tests (unit, integration, e2e)
- **Documentation**: Minimal docstrings in Python code
- **Observability**: Sentry configured but incomplete; no frontend error tracking

### Quirks / Design Choices
1. **Greedy assignment**: Each stop assigned to exactly one nearest building; no ambiguous cases
2. **Per-building clustering**: DBSCAN runs isolated per building; no cross-building entrance clustering
3. **Global percentile normalization**: All buildings normalized against 5-95th percentile of dataset
4. **No dwell time data**: TLC data always has NULL dwell; scoring uses entrance dwell instead
5. **Silent result clipping**: Viewport queries limited to 1000 buildings; no warning if exceeded
6. **Entrance-building association**: Visual only in frontend; no schema constraint

---

## File Inventory

### Database (8 migrations, 100 LOC total)
- `001_enable_postgis.sql` — Extension setup
- `002_create_schema.sql` — Schema creation
- `003_create_tables.sql` — 6 main tables
- `004_create_indexes.sql` — 16 indexes
- `005_create_rpc_functions.sql` — 3 initial RPCs
- `006_validation_and_evidence.sql` — Validation tables + RPC
- `007_validation_tooling.sql` — Rubric + golden tables, constraint fixes
- `008_update_evidence_rpc.sql` — Extended RPC for multi-run queries

### Frontend (16 source files, ~800 LOC)
- **Pages**: `app/page.tsx`, `app/layout.tsx`
- **API Routes**: 4 endpoint files
- **Components**: `MapContainer.tsx`, `MapControls.tsx`, `EvidencePanel.tsx`
- **Hooks**: 3 custom hooks (useMapData, useBuilding, useEvidence)
- **Utils**: Color mapping, geometry math
- **Config**: Supabase client initialization

### Workers (20 source files, ~1500 LOC)
- **Main**: `main.py` (CLI entry, 200 LOC with all subcommands)
- **Common**: `config.py`, `db.py`, `job_tracker.py`, `metrics.py`
- **Pipeline**: `ingest/buildings.py`, `ingest/stops.py`, `cluster/dbscan.py`, `score/compute.py`
- **Validation**: `validate/golden.py`, `validate/rubric.py`, `validate/sanity.py`, `validate/sweep.py`, `validate/compare.py`

---

## Dependencies

### Frontend
- `next@15`, `react@19`, `typescript@5.7`
- `deck.gl@9.1`, `mapbox-gl@3.8`, `react-map-gl@7.1`
- `@supabase/supabase-js@2.45`, `@supabase/ssr@0.5`
- `swr@2.2` (data fetching)
- `tailwindcss@4` (styling)

### Workers
- `psycopg2-binary==2.9.9` — PostgreSQL driver
- `scikit-learn==1.4.1` — DBSCAN clustering
- `pandas==2.2.1`, `pyarrow==15.0.0` — Tabular data + Parquet
- `numpy==1.26.4` — Numerics
- `pyproj==3.6.1` — Coordinate transformations (UTM)
- `shapely==2.0.3` — Geometry validation
- `requests==2.31.0` — HTTP (Overpass API)
- `sentry-sdk==1.40.6` — Error tracking
- `python-dotenv==1.0.1` — .env loading

---

## Recent Commits (Validation Tooling Phase 1)

```
2fbd2c0 Add get_building_evidence_extended RPC for multi-run score queries
6f8bea9 Wire up validation tooling CLI commands in main.py
d303c0b Fix building_scores ON CONFLICT for multi-run parameter sweeps
2b02576 Add validation tooling infrastructure: golden buildings, rubric scoring, parameter sweeps
```

---

## Next Steps (Not Yet Implemented)

- [ ] Frontend UI to submit rubric scores (currently CLI-only)
- [ ] Dedicated sweep results visualization
- [ ] Historical score comparison in map
- [ ] Export buildings/scores/entrances as CSV/GeoJSON
- [ ] Authentication + multi-user support
- [ ] Automated test suite (unit + integration + e2e)
- [ ] API rate limiting
- [ ] Enhanced error handling + user feedback
- [ ] Mobile responsiveness
- [ ] Light theme

---

**Generated**: 2026-03-18
**Author**: Implementation Team
**Audience**: External LLM context, technical partners, code review
