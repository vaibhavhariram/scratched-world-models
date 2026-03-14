"""
Ingest NYC TLC Yellow Taxi stop events and assign them to buildings.

Uses 2014-2016 data which contains raw lat/lng coordinates.
Supports row_limit and bbox overrides for dev workflow.
"""

from io import StringIO
import pandas as pd

from src.common.config import PipelineConfig
from src.common.db import get_connection, get_cursor
from src.common.metrics import compute_assign_metrics, print_summary


TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def run_ingest_stops(job_id: str, year: int, month: int, cfg: PipelineConfig) -> dict:
    """Download one month of Yellow Taxi data and insert Manhattan stop events."""
    url = f"{TLC_BASE_URL}/yellow_tripdata_{year}-{month:02d}.parquet"
    print(f"Downloading {url}...")
    df = pd.read_parquet(url)

    # Normalize column names (they vary across years)
    col_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if "pickup_longitude" in lower or lower == "start_lon":
            col_map[col] = "pickup_lng"
        elif "pickup_latitude" in lower or lower == "start_lat":
            col_map[col] = "pickup_lat"
        elif "dropoff_longitude" in lower or lower == "end_lon":
            col_map[col] = "dropoff_lng"
        elif "dropoff_latitude" in lower or lower == "end_lat":
            col_map[col] = "dropoff_lat"
        elif "pickup_datetime" in lower:
            col_map[col] = "pickup_ts"
        elif "dropoff_datetime" in lower:
            col_map[col] = "dropoff_ts"
        elif "passenger_count" in lower:
            col_map[col] = "passenger_count"
    df = df.rename(columns=col_map)

    required = {"pickup_lng", "pickup_lat", "dropoff_lng", "dropoff_lat", "pickup_ts", "dropoff_ts"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing columns. Found: {list(df.columns)}")

    # Build events
    pickups = df[["pickup_lng", "pickup_lat", "pickup_ts"]].copy()
    pickups.columns = ["lng", "lat", "ts"]
    pickups["event_type"] = "pickup"
    pickups["passenger_count"] = df.get("passenger_count")

    dropoffs = df[["dropoff_lng", "dropoff_lat", "dropoff_ts"]].copy()
    dropoffs.columns = ["lng", "lat", "ts"]
    dropoffs["event_type"] = "dropoff"
    dropoffs["passenger_count"] = df.get("passenger_count")

    events = pd.concat([pickups, dropoffs], ignore_index=True)

    # Filter to bbox
    west, south, east, north = cfg.bbox
    events = events[
        (events["lng"].between(west, east))
        & (events["lat"].between(south, north))
        & (events["lng"] != 0)
        & (events["lat"] != 0)
    ].dropna(subset=["lng", "lat", "ts"])

    # Apply row limit for dev workflow
    if cfg.row_limit and len(events) > cfg.row_limit:
        events = events.head(cfg.row_limit)
        print(f"Row limit applied: {cfg.row_limit} events")

    print(f"Filtered to {len(events)} stop events")

    if cfg.dry_run:
        print(f"[DRY RUN] Would insert {len(events)} stop events")
        return {"total_trips": len(df), "manhattan_events": len(events), "dry_run": True}

    batch_id = job_id

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            buffer = StringIO()
            for _, row in events.iterrows():
                source_id = f"{year}-{month:02d}-{row.name}"
                passenger = int(row["passenger_count"]) if pd.notna(row["passenger_count"]) else "\\N"
                buffer.write(
                    f"{source_id}\t{row['event_type']}\t"
                    f"SRID=4326;POINT({row['lng']} {row['lat']})\t"
                    f"{row['ts']}\t\\N\t{passenger}\tnyc_tlc\t{batch_id}\n"
                )

            buffer.seek(0)
            cur.copy_from(
                buffer, "logistics.stop_events",
                columns=("source_id", "event_type", "location", "event_timestamp",
                         "dwell_seconds", "passenger_count", "source_dataset", "batch_id"),
                null="\\N",
            )
        conn.commit()

    return {
        "year": year, "month": month,
        "total_trips": len(df), "manhattan_events": len(events),
        "batch_id": batch_id,
    }


def run_assign_stops(job_id: str, batch_id: str, cfg: PipelineConfig) -> dict:
    """Assign stop events from a batch to nearest buildings. Idempotent via NOT EXISTS."""
    print(f"Assigning stops from batch {batch_id} (radius={cfg.assignment_radius_m}m)...")

    if cfg.dry_run:
        with get_connection() as conn:
            with get_cursor(conn) as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM logistics.stop_events WHERE batch_id = %s",
                    (batch_id,),
                )
                count = cur.fetchone()[0]
        print(f"[DRY RUN] Would attempt assignment for {count} stops")
        return {"batch_id": batch_id, "stops_to_process": count, "dry_run": True}

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO logistics.building_stop_events (building_id, stop_event_id, distance_m)
                SELECT DISTINCT ON (s.id)
                    b.id, s.id,
                    ST_Distance(ST_Transform(s.location, 32618), ST_Transform(b.footprint, 32618))
                FROM logistics.stop_events s
                JOIN logistics.buildings b
                    ON ST_DWithin(s.location::geography, b.footprint::geography, %s)
                WHERE s.batch_id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM logistics.building_stop_events bse
                      WHERE bse.stop_event_id = s.id
                  )
                ORDER BY s.id, ST_Distance(s.location::geography, b.footprint::geography)
                """,
                (cfg.assignment_radius_m, batch_id),
            )
            assigned = cur.rowcount
        conn.commit()

    metrics = compute_assign_metrics(batch_id)
    metrics["newly_assigned"] = assigned
    print_summary("Assignment Metrics", metrics)
    return metrics
