"""
Run metrics and QA summary helpers.

Computes pipeline-wide stats after each phase and returns
a consistent dict for storage in pipeline_jobs.stats.
"""

from src.common.db import get_connection, get_cursor


def compute_ingest_metrics(batch_id: str) -> dict:
    """Metrics after stop ingestion."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                "SELECT COUNT(*) FROM logistics.stop_events WHERE batch_id = %s",
                (batch_id,),
            )
            stops_ingested = cur.fetchone()[0]
    return {"stops_ingested": stops_ingested}


def compute_assign_metrics(batch_id: str) -> dict:
    """Metrics after building assignment."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Total stops in this batch
            cur.execute(
                "SELECT COUNT(*) FROM logistics.stop_events WHERE batch_id = %s",
                (batch_id,),
            )
            total_stops = cur.fetchone()[0]

            # Assigned stops (those that appear in building_stop_events)
            cur.execute(
                """
                SELECT COUNT(DISTINCT bse.stop_event_id)
                FROM logistics.building_stop_events bse
                JOIN logistics.stop_events s ON s.id = bse.stop_event_id
                WHERE s.batch_id = %s
                """,
                (batch_id,),
            )
            stops_assigned = cur.fetchone()[0]

    unassigned = total_stops - stops_assigned
    rate = round(stops_assigned / total_stops, 4) if total_stops > 0 else 0.0

    return {
        "stops_ingested": total_stops,
        "stops_assigned": stops_assigned,
        "unassigned_stops": unassigned,
        "assignment_rate": rate,
    }


def compute_cluster_metrics(pipeline_run_id: str) -> dict:
    """Metrics after DBSCAN clustering."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Buildings that had enough stops to be eligible
            cur.execute(
                """
                SELECT COUNT(DISTINCT building_id)
                FROM logistics.building_stop_events
                """
            )
            total_with_stops = cur.fetchone()[0]

            # Buildings that produced at least one entrance candidate this run
            cur.execute(
                """
                SELECT COUNT(DISTINCT building_id)
                FROM logistics.entrance_candidates
                WHERE pipeline_run_id = %s
                """,
                (pipeline_run_id,),
            )
            clustered_buildings = cur.fetchone()[0]

            # Total entrance candidates created this run
            cur.execute(
                """
                SELECT COUNT(*)
                FROM logistics.entrance_candidates
                WHERE pipeline_run_id = %s
                """,
                (pipeline_run_id,),
            )
            entrance_candidates = cur.fetchone()[0]

    return {
        "eligible_buildings": total_with_stops,
        "clustered_buildings": clustered_buildings,
        "entrance_candidates_created": entrance_candidates,
    }


def compute_score_metrics(pipeline_run_id: str) -> dict:
    """Metrics after score computation."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM logistics.building_scores
                WHERE pipeline_run_id = %s
                """,
                (pipeline_run_id,),
            )
            scored = cur.fetchone()[0]

            # Distribution summary
            cur.execute(
                """
                SELECT
                    MIN(difficulty), MAX(difficulty),
                    AVG(difficulty), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY difficulty)
                FROM logistics.building_scores
                WHERE pipeline_run_id = %s
                """,
                (pipeline_run_id,),
            )
            row = cur.fetchone()

    return {
        "scored_buildings": scored,
        "difficulty_min": round(row[0], 4) if row[0] else None,
        "difficulty_max": round(row[1], 4) if row[1] else None,
        "difficulty_mean": round(row[2], 4) if row[2] else None,
        "difficulty_median": round(row[3], 4) if row[3] else None,
    }


def print_summary(label: str, metrics: dict) -> None:
    """Print a formatted QA summary to stdout."""
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    for k, v in metrics.items():
        print(f"  {k:.<35} {v}")
    print()
