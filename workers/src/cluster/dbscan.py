"""
DBSCAN clustering pipeline with targeted rerun support.

Supports running against:
- all buildings (default)
- a single building_id
- buildings within a bbox
- buildings from a specific pipeline_run_id (re-cluster)
"""

import math
import numpy as np
from pyproj import Transformer
from sklearn.cluster import DBSCAN

from src.common.config import PipelineConfig
from src.common.db import get_connection, get_cursor
from src.common.metrics import compute_cluster_metrics, print_summary

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:32618", "EPSG:4326", always_xy=True)


def _compute_confidence(cluster_size: int, stddev: float) -> float:
    size_score = 1 - math.exp(-cluster_size / 20)
    spread_score = max(0, 1 - stddev / 10)
    return round(0.6 * size_score + 0.4 * spread_score, 3)


def _determine_side(ex: float, ey: float, cx: float, cy: float) -> str:
    dx, dy = ex - cx, ey - cy
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "north" if dy > 0 else "south"


def _cluster_building(building_id: int, conn, cfg: PipelineConfig) -> list[dict]:
    """Run DBSCAN on stops near one building."""
    with get_cursor(conn) as cur:
        cur.execute(
            """
            SELECT s.id, ST_X(s.location), ST_Y(s.location),
                   COALESCE(s.dwell_seconds, 0)
            FROM logistics.stop_events s
            JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
            WHERE bse.building_id = %s
            """,
            (building_id,),
        )
        rows = cur.fetchall()

    if len(rows) < cfg.min_building_samples:
        return []

    lngs = [r[1] for r in rows]
    lats = [r[2] for r in rows]
    dwells = np.array([r[3] for r in rows])

    xs, ys = _to_utm.transform(lngs, lats)
    coords = np.column_stack([xs, ys])

    with get_cursor(conn) as cur:
        cur.execute(
            "SELECT ST_X(centroid), ST_Y(centroid) FROM logistics.buildings WHERE id = %s",
            (building_id,),
        )
        bld_row = cur.fetchone()
    bld_cx, bld_cy = _to_utm.transform(bld_row[0], bld_row[1])

    clustering = DBSCAN(eps=cfg.dbscan_eps_m, min_samples=cfg.dbscan_min_samples).fit(coords)
    labels = clustering.labels_

    entrances = []
    for label in set(labels):
        if label == -1:
            continue
        mask = labels == label
        cc = coords[mask]
        cd = dwells[mask]
        cx, cy = float(cc[:, 0].mean()), float(cc[:, 1].mean())
        stddev = float(cc.std())
        lng, lat = _to_wgs.transform(cx, cy)
        cluster_size = int(mask.sum())

        entrances.append({
            "building_id": building_id,
            "lng": lng, "lat": lat,
            "cluster_size": cluster_size,
            "avg_dwell_sec": float(cd.mean()),
            "stddev_position": stddev,
            "confidence": _compute_confidence(cluster_size, stddev),
            "side": _determine_side(cx, cy, bld_cx, bld_cy),
        })

    return entrances


def _resolve_building_ids(
    conn,
    cfg: PipelineConfig,
    job_id: str,
    building_id: int | None = None,
    target_bbox: tuple[float, float, float, float] | None = None,
    rerun_pipeline_id: str | None = None,
) -> list[int]:
    """Resolve which buildings to cluster based on targeting parameters."""
    with get_cursor(conn) as cur:
        if building_id:
            return [building_id]

        if rerun_pipeline_id:
            # Re-cluster buildings from a previous run
            cur.execute(
                """
                SELECT DISTINCT building_id
                FROM logistics.entrance_candidates
                WHERE pipeline_run_id = %s
                """,
                (rerun_pipeline_id,),
            )
            return [r[0] for r in cur.fetchall()]

        if target_bbox:
            west, south, east, north = target_bbox
            cur.execute(
                """
                SELECT DISTINCT bse.building_id
                FROM logistics.building_stop_events bse
                JOIN logistics.buildings b ON b.id = bse.building_id
                WHERE b.footprint && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                GROUP BY bse.building_id
                HAVING COUNT(*) >= %s
                """,
                (west, south, east, north, cfg.min_building_samples),
            )
            return [r[0] for r in cur.fetchall()]

        # Default: all eligible buildings not yet processed in this run
        cur.execute(
            """
            SELECT DISTINCT bse.building_id
            FROM logistics.building_stop_events bse
            WHERE NOT EXISTS (
                SELECT 1 FROM logistics.entrance_candidates ec
                WHERE ec.building_id = bse.building_id
                  AND ec.pipeline_run_id = %s
            )
            GROUP BY bse.building_id
            HAVING COUNT(*) >= %s
            """,
            (job_id, cfg.min_building_samples),
        )
        return [r[0] for r in cur.fetchall()]


def run_clustering(
    job_id: str,
    cfg: PipelineConfig,
    building_id: int | None = None,
    target_bbox: tuple[float, float, float, float] | None = None,
    rerun_pipeline_id: str | None = None,
) -> dict:
    """Run DBSCAN clustering. Supports targeted reruns."""
    with get_connection() as conn:
        building_ids = _resolve_building_ids(
            conn, cfg, job_id, building_id, target_bbox, rerun_pipeline_id
        )
        print(f"Clustering {len(building_ids)} buildings "
              f"(eps={cfg.dbscan_eps_m}m, min_samples={cfg.dbscan_min_samples})...")

        if cfg.dry_run:
            print(f"[DRY RUN] Would cluster {len(building_ids)} buildings")
            return {"buildings_to_cluster": len(building_ids), "dry_run": True}

        # If re-running, clear previous results for these buildings
        if rerun_pipeline_id or building_id:
            with get_cursor(conn) as cur:
                for bid in building_ids:
                    cur.execute(
                        "DELETE FROM logistics.entrance_candidates WHERE building_id = %s",
                        (bid,),
                    )
            conn.commit()

        total_entrances = 0
        processed = 0

        for bid in building_ids:
            entrances = _cluster_building(bid, conn, cfg)
            if entrances:
                with get_cursor(conn) as cur:
                    for e in entrances:
                        cur.execute(
                            """
                            INSERT INTO logistics.entrance_candidates
                                (building_id, location, cluster_size, avg_dwell_sec,
                                 stddev_position, confidence, side, pipeline_run_id)
                            VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                                    %s, %s, %s, %s, %s, %s)
                            """,
                            (e["building_id"], e["lng"], e["lat"],
                             e["cluster_size"], e["avg_dwell_sec"],
                             e["stddev_position"], e["confidence"], e["side"], job_id),
                        )
                        total_entrances += 1
                conn.commit()

            processed += 1
            if processed % 100 == 0:
                print(f"  Progress: {processed}/{len(building_ids)}, {total_entrances} entrances")

    metrics = compute_cluster_metrics(job_id)
    metrics["buildings_targeted"] = len(building_ids)
    print_summary("Clustering Metrics", metrics)
    return metrics
