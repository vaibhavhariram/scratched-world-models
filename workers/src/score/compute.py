"""
Delivery difficulty score computation.

Computes a composite difficulty score (0-1) for each building based on:
- stop_variance: spatial spread of stops (high = harder to find entrance)
- road_distance: avg distance from building edge (far = harder access)
- entrance_count: number of inferred entrances (many = ambiguous)
- dwell_time: avg dwell time at entrances (long = harder delivery)

Scores are normalized against dataset-wide percentiles.
"""

import numpy as np

from src.common.config import SCORE_WEIGHTS
from src.common.db import get_connection, get_cursor


def _compute_global_stats(conn) -> dict:
    """Compute dataset-wide min/max for each scoring dimension."""
    with get_cursor(conn) as cur:
        # Stop variance per building
        cur.execute(
            """
            SELECT building_id,
                   STDDEV(ST_X(ST_Transform(s.location, 32618))) +
                   STDDEV(ST_Y(ST_Transform(s.location, 32618))) AS spatial_stddev
            FROM logistics.stop_events s
            JOIN logistics.building_stop_events bse ON bse.stop_event_id = s.id
            GROUP BY building_id
            HAVING COUNT(*) >= 5
            """
        )
        variances = [r[1] for r in cur.fetchall() if r[1] is not None]

        # Road distance per building
        cur.execute(
            "SELECT AVG(distance_m) FROM logistics.building_stop_events GROUP BY building_id"
        )
        distances = [r[0] for r in cur.fetchall() if r[0] is not None]

        # Entrance count per building
        cur.execute(
            "SELECT COUNT(*) FROM logistics.entrance_candidates GROUP BY building_id"
        )
        entrance_counts = [r[0] for r in cur.fetchall()]

        # Dwell time per building
        cur.execute(
            "SELECT AVG(avg_dwell_sec) FROM logistics.entrance_candidates GROUP BY building_id"
        )
        dwells = [r[0] for r in cur.fetchall() if r[0] is not None]

    def percentile_range(values):
        if not values:
            return (0, 1)
        arr = np.array(values)
        return (float(np.percentile(arr, 5)), float(np.percentile(arr, 95)))

    return {
        "variance": percentile_range(variances),
        "road_dist": percentile_range(distances),
        "entrance_ct": percentile_range(entrance_counts),
        "dwell": percentile_range(dwells),
    }


def _normalize(value: float, range_tuple: tuple[float, float]) -> float:
    """Normalize a value to 0-1 using the given (min, max) range, clamped."""
    lo, hi = range_tuple
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def run_scoring(job_id: str) -> dict:
    """Compute delivery difficulty scores for all buildings with entrance candidates."""
    with get_connection() as conn:
        print("Computing global statistics for normalization...")
        global_stats = _compute_global_stats(conn)
        print(f"  Ranges: {global_stats}")

        with get_cursor(conn) as cur:
            # Get buildings that have entrance candidates but no score for this run
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
            building_ids = [r[0] for r in cur.fetchall()]

        print(f"Scoring {len(building_ids)} buildings...")
        scored = 0

        for bid in building_ids:
            with get_cursor(conn) as cur:
                # Stop variance
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
                stop_variance_raw = row[0] or 0
                sample_size = row[1]

                # Road distance
                cur.execute(
                    "SELECT AVG(distance_m) FROM logistics.building_stop_events WHERE building_id = %s",
                    (bid,),
                )
                road_dist_raw = cur.fetchone()[0] or 0

                # Entrance count
                cur.execute(
                    "SELECT COUNT(*) FROM logistics.entrance_candidates WHERE building_id = %s",
                    (bid,),
                )
                entrance_ct_raw = cur.fetchone()[0]

                # Dwell time
                cur.execute(
                    "SELECT AVG(avg_dwell_sec) FROM logistics.entrance_candidates WHERE building_id = %s",
                    (bid,),
                )
                dwell_raw = cur.fetchone()[0] or 0

            # Normalize
            sub_scores = {
                "stop_variance": _normalize(stop_variance_raw, global_stats["variance"]),
                "road_distance": _normalize(road_dist_raw, global_stats["road_dist"]),
                "entrance_count": _normalize(entrance_ct_raw, global_stats["entrance_ct"]),
                "dwell_time": _normalize(dwell_raw, global_stats["dwell"]),
            }

            difficulty = sum(SCORE_WEIGHTS[k] * sub_scores[k] for k in SCORE_WEIGHTS)

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
                    (
                        bid,
                        round(difficulty, 4),
                        round(sub_scores["stop_variance"], 4),
                        round(sub_scores["road_distance"], 4),
                        round(sub_scores["entrance_count"], 4),
                        round(sub_scores["dwell_time"], 4),
                        sample_size,
                        job_id,
                    ),
                )
            conn.commit()

            scored += 1
            if scored % 100 == 0:
                print(f"  Progress: {scored}/{len(building_ids)}")

    stats = {"buildings_scored": scored}
    print(f"Scoring complete: {stats}")
    return stats
