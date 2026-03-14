"""
Delivery difficulty score computation with targeted rerun support.

Supports scoring:
- all buildings with entrance candidates (default)
- a single building_id
- buildings within a bbox
- buildings from a specific pipeline_run_id
"""

import numpy as np

from src.common.config import PipelineConfig
from src.common.db import get_connection, get_cursor
from src.common.metrics import compute_score_metrics, print_summary


def _compute_global_stats(conn) -> dict:
    """Compute dataset-wide percentile ranges for normalization."""
    with get_cursor(conn) as cur:
        cur.execute(
            """
            SELECT building_id,
                   STDDEV(ST_X(ST_Transform(s.location, 32618))) +
                   STDDEV(ST_Y(ST_Transform(s.location, 32618)))
            FROM logistics.stop_events s
            JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
            GROUP BY building_id HAVING COUNT(*) >= 5
            """
        )
        variances = [r[1] for r in cur.fetchall() if r[1] is not None]

        cur.execute("SELECT AVG(distance_m) FROM logistics.building_stop_events GROUP BY building_id")
        distances = [r[0] for r in cur.fetchall() if r[0] is not None]

        cur.execute("SELECT COUNT(*) FROM logistics.entrance_candidates GROUP BY building_id")
        entrance_counts = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT AVG(avg_dwell_sec) FROM logistics.entrance_candidates GROUP BY building_id")
        dwells = [r[0] for r in cur.fetchall() if r[0] is not None]

    def pct_range(values):
        if not values:
            return (0, 1)
        arr = np.array(values)
        return (float(np.percentile(arr, 5)), float(np.percentile(arr, 95)))

    return {
        "variance": pct_range(variances),
        "road_dist": pct_range(distances),
        "entrance_ct": pct_range(entrance_counts),
        "dwell": pct_range(dwells),
    }


def _normalize(value: float, lo_hi: tuple[float, float]) -> float:
    lo, hi = lo_hi
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _resolve_building_ids(
    conn,
    job_id: str,
    building_id: int | None = None,
    target_bbox: tuple[float, float, float, float] | None = None,
    rerun_pipeline_id: str | None = None,
) -> list[int]:
    """Resolve which buildings to score."""
    with get_cursor(conn) as cur:
        if building_id:
            return [building_id]

        if rerun_pipeline_id:
            cur.execute(
                "SELECT DISTINCT building_id FROM logistics.entrance_candidates WHERE pipeline_run_id = %s",
                (rerun_pipeline_id,),
            )
            return [r[0] for r in cur.fetchall()]

        if target_bbox:
            west, south, east, north = target_bbox
            cur.execute(
                """
                SELECT DISTINCT ec.building_id
                FROM logistics.entrance_candidates ec
                JOIN logistics.buildings b ON b.id = ec.building_id
                WHERE b.footprint && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                """,
                (west, south, east, north),
            )
            return [r[0] for r in cur.fetchall()]

        # Default: all buildings with entrances, skip already scored this run
        cur.execute(
            """
            SELECT DISTINCT ec.building_id
            FROM logistics.entrance_candidates ec
            WHERE NOT EXISTS (
                SELECT 1 FROM logistics.building_scores bs
                WHERE bs.building_id = ec.building_id
                  AND bs.pipeline_run_id = %s
            )
            """,
            (job_id,),
        )
        return [r[0] for r in cur.fetchall()]


def run_scoring(
    job_id: str,
    cfg: PipelineConfig,
    building_id: int | None = None,
    target_bbox: tuple[float, float, float, float] | None = None,
    rerun_pipeline_id: str | None = None,
) -> dict:
    """Compute difficulty scores. Supports targeted reruns."""
    with get_connection() as conn:
        print("Computing global normalization stats...")
        global_stats = _compute_global_stats(conn)
        print(f"  Ranges: {global_stats}")

        building_ids = _resolve_building_ids(
            conn, job_id, building_id, target_bbox, rerun_pipeline_id
        )
        print(f"Scoring {len(building_ids)} buildings...")

        if cfg.dry_run:
            print(f"[DRY RUN] Would score {len(building_ids)} buildings")
            return {"buildings_to_score": len(building_ids), "dry_run": True}

        weights = cfg.score_weights
        scored = 0

        for bid in building_ids:
            with get_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT STDDEV(ST_X(ST_Transform(s.location, 32618))) +
                           STDDEV(ST_Y(ST_Transform(s.location, 32618))),
                           COUNT(*)
                    FROM logistics.stop_events s
                    JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
                    WHERE bse.building_id = %s
                    """,
                    (bid,),
                )
                row = cur.fetchone()
                stop_var = row[0] or 0
                sample_size = row[1]

                cur.execute("SELECT AVG(distance_m) FROM logistics.building_stop_events WHERE building_id = %s", (bid,))
                road_dist = cur.fetchone()[0] or 0

                cur.execute("SELECT COUNT(*) FROM logistics.entrance_candidates WHERE building_id = %s", (bid,))
                ent_ct = cur.fetchone()[0]

                cur.execute("SELECT AVG(avg_dwell_sec) FROM logistics.entrance_candidates WHERE building_id = %s", (bid,))
                dwell = cur.fetchone()[0] or 0

            sub = {
                "stop_variance": _normalize(stop_var, global_stats["variance"]),
                "road_distance": _normalize(road_dist, global_stats["road_dist"]),
                "entrance_count": _normalize(ent_ct, global_stats["entrance_ct"]),
                "dwell_time": _normalize(dwell, global_stats["dwell"]),
            }
            difficulty = sum(weights[k] * sub[k] for k in weights)

            with get_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO logistics.building_scores
                        (building_id, difficulty, stop_variance, road_distance,
                         entrance_count, dwell_time, sample_size, pipeline_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (building_id) DO UPDATE SET
                        difficulty = EXCLUDED.difficulty,
                        stop_variance = EXCLUDED.stop_variance,
                        road_distance = EXCLUDED.road_distance,
                        entrance_count = EXCLUDED.entrance_count,
                        dwell_time = EXCLUDED.dwell_time,
                        sample_size = EXCLUDED.sample_size,
                        pipeline_run_id = EXCLUDED.pipeline_run_id,
                        computed_at = now()
                    """,
                    (bid, round(difficulty, 4),
                     round(sub["stop_variance"], 4), round(sub["road_distance"], 4),
                     round(sub["entrance_count"], 4), round(sub["dwell_time"], 4),
                     sample_size, job_id),
                )
            conn.commit()
            scored += 1
            if scored % 100 == 0:
                print(f"  Progress: {scored}/{len(building_ids)}")

    metrics = compute_score_metrics(job_id)
    metrics["buildings_targeted"] = len(building_ids)
    print_summary("Scoring Metrics", metrics)
    return metrics
