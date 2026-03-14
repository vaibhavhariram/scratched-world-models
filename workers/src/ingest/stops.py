"""
Ingest NYC TLC Yellow Taxi stop events and assign them to buildings.

Uses 2014-2016 data which contains raw lat/lng coordinates.
Post-2016 data uses LocationID zones and is not suitable for this pipeline.
"""

import uuid
from io import StringIO

import pandas as pd

from src.common.config import MANHATTAN_BBOX, BUILDING_ASSIGN_DISTANCE_M
from src.common.db import get_connection, get_cursor


TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def run_ingest_stops(job_id: str, year: int, month: int) -> dict:
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

    # Build pickup events
    pickups = df[["pickup_lng", "pickup_lat", "pickup_ts"]].copy()
    pickups.columns = ["lng", "lat", "ts"]
    pickups["event_type"] = "pickup"
    if "passenger_count" in df.columns:
        pickups["passenger_count"] = df["passenger_count"]
    else:
        pickups["passenger_count"] = None

    # Build dropoff events
    dropoffs = df[["dropoff_lng", "dropoff_lat", "dropoff_ts"]].copy()
    dropoffs.columns = ["lng", "lat", "ts"]
    dropoffs["event_type"] = "dropoff"
    if "passenger_count" in df.columns:
        dropoffs["passenger_count"] = df["passenger_count"]
    else:
        dropoffs["passenger_count"] = None

    events = pd.concat([pickups, dropoffs], ignore_index=True)

    # Filter to Manhattan bounding box and remove invalid coordinates
    west, south, east, north = MANHATTAN_BBOX
    events = events[
        (events["lng"].between(west, east))
        & (events["lat"].between(south, north))
        & (events["lng"] != 0)
        & (events["lat"] != 0)
    ].dropna(subset=["lng", "lat", "ts"])

    print(f"Filtered to {len(events)} Manhattan stop events")

    batch_id = job_id
    inserted = 0

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Use COPY for bulk insert performance
            buffer = StringIO()
            for _, row in events.iterrows():
                source_id = f"{year}-{month:02d}-{row.name}"
                passenger = int(row["passenger_count"]) if pd.notna(row["passenger_count"]) else "\\N"
                line = (
                    f"{source_id}\t"
                    f"{row['event_type']}\t"
                    f"SRID=4326;POINT({row['lng']} {row['lat']})\t"
                    f"{row['ts']}\t"
                    f"\\N\t"  # dwell_seconds
                    f"{passenger}\t"
                    f"nyc_tlc\t"
                    f"{batch_id}\n"
                )
                buffer.write(line)
                inserted += 1

            buffer.seek(0)
            cur.copy_from(
                buffer,
                "logistics.stop_events",
                columns=(
                    "source_id",
                    "event_type",
                    "location",
                    "event_timestamp",
                    "dwell_seconds",
                    "passenger_count",
                    "source_dataset",
                    "batch_id",
                ),
                null="\\N",
            )
        conn.commit()

    stats = {
        "year": year,
        "month": month,
        "total_trips": len(df),
        "manhattan_events": inserted,
        "batch_id": batch_id,
    }
    print(f"Stop ingestion complete: {stats}")
    return stats


def run_assign_stops(job_id: str, batch_id: str) -> dict:
    """Assign stop events from a batch to their nearest buildings."""
    print(f"Assigning stops from batch {batch_id} to buildings...")

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO logistics.building_stop_events (building_id, stop_event_id, distance_m)
                SELECT DISTINCT ON (s.id)
                    b.id AS building_id,
                    s.id AS stop_event_id,
                    ST_Distance(
                        ST_Transform(s.location, 32618),
                        ST_Transform(b.footprint, 32618)
                    ) AS distance_m
                FROM logistics.stop_events s
                JOIN logistics.buildings b
                    ON ST_DWithin(
                        s.location::geography,
                        b.footprint::geography,
                        %s
                    )
                WHERE s.batch_id = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM logistics.building_stop_events bse
                      WHERE bse.stop_event_id = s.id
                  )
                ORDER BY s.id, ST_Distance(s.location::geography, b.footprint::geography)
                """,
                (BUILDING_ASSIGN_DISTANCE_M, batch_id),
            )
            assigned = cur.rowcount
        conn.commit()

    stats = {"batch_id": batch_id, "assigned": assigned}
    print(f"Stop assignment complete: {stats}")
    return stats
