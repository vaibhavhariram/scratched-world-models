"""
DBSCAN clustering pipeline.

For each building with sufficient stop events, runs DBSCAN to identify
spatial clusters that suggest entrance locations. Each cluster centroid
becomes an entrance candidate with confidence scoring.
"""

import math

import numpy as np
from pyproj import Transformer
from sklearn.cluster import DBSCAN

from src.common.config import DBSCAN_EPS_METERS, DBSCAN_MIN_SAMPLES, MIN_STOPS_FOR_CLUSTERING
from src.common.db import get_connection, get_cursor

# UTM Zone 18N (Manhattan) <-> WGS84
_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:32618", "EPSG:4326", always_xy=True)


def _compute_confidence(cluster_size: int, stddev: float) -> float:
    """
    Confidence score based on cluster density.

    Higher cluster size and lower spatial spread → higher confidence.
    """
    # Sigmoid-like scaling for cluster size (saturates around 50)
    size_score = 1 - math.exp(-cluster_size / 20)
    # Lower stddev is better; penalize spread > 10m
    spread_score = max(0, 1 - stddev / 10)
    return round(0.6 * size_score + 0.4 * spread_score, 3)


def _determine_side(entrance_x: float, entrance_y: float, centroid_x: float, centroid_y: float) -> str:
    """Determine which side of the building the entrance is on."""
    dx = entrance_x - centroid_x
    dy = entrance_y - centroid_y
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def _cluster_building(building_id: int, conn) -> list[dict]:
    """Run DBSCAN on stops near one building to find entrance clusters."""
    with get_cursor(conn) as cur:
        cur.execute(
            """
            SELECT s.id,
                   ST_X(s.location) AS lng,
                   ST_Y(s.location) AS lat,
                   COALESCE(s.dwell_seconds, 0) AS dwell
            FROM logistics.stop_events s
            JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
            WHERE bse.building_id = %s
            """,
            (building_id,),
        )
        rows = cur.fetchall()

    if len(rows) < MIN_STOPS_FOR_CLUSTERING:
        return []

    # Project to UTM for metric distance
    lngs = [r[1] for r in rows]
    lats = [r[2] for r in rows]
    dwells = np.array([r[3] for r in rows])

    xs, ys = _to_utm.transform(lngs, lats)
    coords = np.column_stack([xs, ys])

    # Get building centroid in UTM for side determination
    with get_cursor(conn) as cur:
        cur.execute(
            "SELECT ST_X(centroid), ST_Y(centroid) FROM logistics.buildings WHERE id = %s",
            (building_id,),
        )
        bld_row = cur.fetchone()

    bld_cx, bld_cy = _to_utm.transform(bld_row[0], bld_row[1])

    # Run DBSCAN
    clustering = DBSCAN(eps=DBSCAN_EPS_METERS, min_samples=DBSCAN_MIN_SAMPLES).fit(coords)
    labels = clustering.labels_

    entrances = []
    for label in set(labels):
        if label == -1:
            continue

        mask = labels == label
        cluster_coords = coords[mask]
        cluster_dwells = dwells[mask]

        centroid_x = float(cluster_coords[:, 0].mean())
        centroid_y = float(cluster_coords[:, 1].mean())
        stddev = float(cluster_coords.std())

        # Convert centroid back to WGS84
        lng, lat = _to_wgs.transform(centroid_x, centroid_y)

        cluster_size = int(mask.sum())
        confidence = _compute_confidence(cluster_size, stddev)
        side = _determine_side(centroid_x, centroid_y, bld_cx, bld_cy)

        entrances.append({
            "building_id": building_id,
            "lng": lng,
            "lat": lat,
            "cluster_size": cluster_size,
            "avg_dwell_sec": float(cluster_dwells.mean()),
            "stddev_position": stddev,
            "confidence": confidence,
            "side": side,
        })

    return entrances


def run_clustering(job_id: str) -> dict:
    """Run DBSCAN clustering across all buildings with assigned stops."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Find buildings that need clustering (skip already-processed ones for this run)
            cur.execute(
                """
                SELECT DISTINCT bse.building_id
                FROM logistics.building_stop_events bse
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM logistics.entrance_candidates ec
                    WHERE ec.building_id = bse.building_id
                      AND ec.pipeline_run_id = %s
                )
                GROUP BY bse.building_id
                HAVING COUNT(*) >= %s
                """,
                (job_id, MIN_STOPS_FOR_CLUSTERING),
            )
            building_ids = [r[0] for r in cur.fetchall()]

        print(f"Clustering {len(building_ids)} buildings...")
        total_entrances = 0
        buildings_processed = 0

        for bid in building_ids:
            entrances = _cluster_building(bid, conn)

            if entrances:
                with get_cursor(conn) as cur:
                    for e in entrances:
                        cur.execute(
                            """
                            INSERT INTO logistics.entrance_candidates
                                (building_id, location, cluster_size, avg_dwell_sec,
                                 stddev_position, confidence, side, pipeline_run_id)
                            VALUES (
                                %s,
                                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                %s, %s, %s, %s, %s, %s
                            )
                            """,
                            (
                                e["building_id"],
                                e["lng"],
                                e["lat"],
                                e["cluster_size"],
                                e["avg_dwell_sec"],
                                e["stddev_position"],
                                e["confidence"],
                                e["side"],
                                job_id,
                            ),
                        )
                        total_entrances += 1
                conn.commit()  # Commit per building for restartability

            buildings_processed += 1
            if buildings_processed % 100 == 0:
                print(f"  Progress: {buildings_processed}/{len(building_ids)} buildings, {total_entrances} entrances")

    stats = {
        "buildings_processed": buildings_processed,
        "total_entrances": total_entrances,
    }
    print(f"Clustering complete: {stats}")
    return stats
