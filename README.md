# Logistics World Graph

Infer building entrance locations and delivery difficulty scores from taxi trajectory stop data. Manhattan MVP using NYC TLC taxi data + OpenStreetMap building footprints.

## Architecture

- **Frontend**: Next.js + deck.gl/Mapbox (`web/`)
- **Database**: Supabase Postgres + PostGIS (`supabase/`)
- **Workers**: Python pipeline — ingestion, clustering, scoring (`workers/`)

## Quick Start

### Database
Run migrations in order against your Supabase project:
```
supabase/migrations/001_enable_postgis.sql → 006_validation_and_evidence.sql
```

### Workers
```bash
cd workers
pip install -r requirements.txt
cp .env.example .env  # fill in DATABASE_URL

# Full pipeline
python -m src.main ingest-buildings
python -m src.main ingest-stops --year 2015 --month 1
python -m src.main assign --batch-id <job-id>
python -m src.main cluster
python -m src.main score

# Dev workflow: small slice
python -m src.main ingest-stops --year 2015 --month 1 --row-limit 10000
python -m src.main cluster --dry-run
python -m src.main cluster --building-id 42
python -m src.main cluster --bbox=-74.01,40.71,-73.97,40.75
python -m src.main cluster --eps 8 --min-samples 5
python -m src.main score --rerun-pipeline <uuid>
```

### Frontend
```bash
cd web
npm install
cp .env.local.example .env.local  # fill in keys
npm run dev
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/buildings?bbox=w,s,e,n` | Buildings in bounding box (GeoJSON) |
| `GET /api/buildings/:id` | Single building with entrances + score |
| `GET /api/buildings/:id/evidence` | Full debug evidence (stops, entrances, score, validation notes) |
| `GET /api/entrances?bbox=w,s,e,n` | Entrance candidates in bounding box |

## Pipeline Parameters

| Parameter | Default | CLI Flag |
|---|---|---|
| Assignment radius | 50m | `--assignment-radius` |
| DBSCAN eps | 5m | `--eps` |
| DBSCAN min_samples | 3 | `--min-samples` |
| Min building samples | 5 | `--min-building-samples` |
| Row limit | unlimited | `--row-limit` |
| Dry run | false | `--dry-run` |

## Validation Tooling

Validation commands help you test, tune, and verify the pipeline on real data.

### Golden Buildings
Select a curated set of buildings to manually review across all parameter sweeps:
```bash
# Add buildings to golden set
python -m src.main golden-add --building-ids 101,204,305 --reason "diverse size/type"

# List golden buildings with stop counts
python -m src.main golden-list

# Remove from set
python -m src.main golden-remove --building-ids 101
```

### Sanity Checks
Run data quality checks on assigned stops:
```bash
# Check all buildings
python -m src.main sanity-check

# Check a single building
python -m src.main sanity-check --building-id 101
```

Detects: zero coordinates, duplicate stops, suspicious spatial extent.

### Rubric Scoring
Score individual buildings on 0-3 scales:
- **Assignment quality**: Do stops belong to the right building?
- **Entrance plausibility**: Are inferred entrances on real building facades?
- **Score usefulness**: Is the difficulty score directionally correct?

```bash
# Score a single building
python -m src.main rubric --pipeline-run-id <uuid> --building-id 101 \
    --assignment 2 --entrance 3 --score 1 --note "entrances good, score seems off"

# Interactive batch scoring of all golden buildings
python -m src.main rubric-batch --pipeline-run-id <uuid>
```

### Parameter Sweeps
Test multiple clustering parameter combinations in a single run:
```bash
python -m src.main sweep \
    --eps 3,5,7 \
    --min-samples 2,3,5 \
    --tag "march-tuning-v1"
```

This runs 3 × 3 = 9 sweeps, each tagged for comparison.

### Run Comparison
Compare sweep results side by side:
```bash
# Compare specific runs
python -m src.main compare --run-ids <uuid1>,<uuid2>,<uuid3>

# Compare all runs with a sweep tag
python -m src.main compare --tag "march-tuning-v1"
```

Shows: metrics per run, golden building details, rubric averages.

## Typical Validation Workflow

1. **Run small dataset**: 1 month, 1 city, current parameters
2. **Add golden buildings**: Select 20-30 diverse buildings
3. **Score golden buildings**: Manually review with `rubric-batch`
4. **Tune parameters**: Run `sweep` with different eps/min_samples values
5. **Compare results**: Use `compare` to pick best parameter combo
6. **Lock baseline**: Use best params for full production runs

## Database Schema

Key tables added for validation:
- `logistics.golden_buildings`: curated set of buildings to review
- `logistics.building_rubric_scores`: quantitative validation scores (per building, per run)
- `logistics.building_validation_notes`: qualitative status labels (plausible, wrong_building, etc.)
