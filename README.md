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
