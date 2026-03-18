"""Rubric scoring: quantitative validation of pipeline results."""

from src.common.db import get_connection, get_cursor
from src.validate.golden import list_golden_buildings
import json


def upsert_rubric(
    building_id: int,
    pipeline_run_id: str,
    assignment_quality: int,
    entrance_plausibility: int,
    score_usefulness: int,
    note: str | None = None,
) -> None:
    """Insert or update a rubric score for one building+run."""
    if not all(0 <= s <= 3 for s in [assignment_quality, entrance_plausibility, score_usefulness]):
        raise ValueError("All rubric scores must be 0-3")

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute("""
                INSERT INTO logistics.building_rubric_scores
                    (building_id, pipeline_run_id, assignment_quality, entrance_plausibility, score_usefulness, note)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (building_id, pipeline_run_id) DO UPDATE SET
                    assignment_quality = EXCLUDED.assignment_quality,
                    entrance_plausibility = EXCLUDED.entrance_plausibility,
                    score_usefulness = EXCLUDED.score_usefulness,
                    note = EXCLUDED.note,
                    created_at = now()
            """, (building_id, pipeline_run_id, assignment_quality, entrance_plausibility, score_usefulness, note))
            conn.commit()


def get_rubric_summary(pipeline_run_id: str) -> dict:
    """Return avg rubric scores and count for a run."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as count,
                    ROUND(AVG(assignment_quality)::numeric, 2) as avg_assignment,
                    ROUND(AVG(entrance_plausibility)::numeric, 2) as avg_entrance,
                    ROUND(AVG(score_usefulness)::numeric, 2) as avg_score
                FROM logistics.building_rubric_scores
                WHERE pipeline_run_id = %s
            """, (pipeline_run_id,))
            row = cur.fetchone()
            return {
                "count": row[0],
                "avg_assignment_quality": float(row[1]) if row[1] else None,
                "avg_entrance_plausibility": float(row[2]) if row[2] else None,
                "avg_score_usefulness": float(row[3]) if row[3] else None,
            }


def get_building_evidence_for_rubric(building_id: int, pipeline_run_id: str) -> dict:
    """Fetch evidence for a building to help with rubric scoring."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            # Building info
            cur.execute("""
                SELECT name, address, building_type, area_sqm
                FROM logistics.buildings
                WHERE id = %s
            """, (building_id,))
            b_row = cur.fetchone()

            # Score
            cur.execute("""
                SELECT difficulty, stop_variance, road_distance, entrance_count, dwell_time, sample_size
                FROM logistics.building_scores
                WHERE building_id = %s AND pipeline_run_id = %s
            """, (building_id, pipeline_run_id))
            s_row = cur.fetchone()

            # Entrance candidates
            cur.execute("""
                SELECT cluster_size, confidence, side, avg_dwell_sec, stddev_position
                FROM logistics.entrance_candidates
                WHERE building_id = %s AND pipeline_run_id = %s
                ORDER BY confidence DESC
            """, (building_id, pipeline_run_id))
            entrances = cur.fetchall()

            return {
                "building": {
                    "id": building_id,
                    "name": b_row[0] if b_row else None,
                    "address": b_row[1] if b_row else None,
                    "type": b_row[2] if b_row else None,
                    "area_sqm": float(b_row[3]) if b_row and b_row[3] else None,
                },
                "score": {
                    "difficulty": float(s_row[0]) if s_row and s_row[0] else None,
                    "stop_variance": float(s_row[1]) if s_row and s_row[1] else None,
                    "road_distance": float(s_row[2]) if s_row and s_row[2] else None,
                    "entrance_count": float(s_row[3]) if s_row and s_row[3] else None,
                    "dwell_time": float(s_row[4]) if s_row and s_row[4] else None,
                    "sample_size": int(s_row[5]) if s_row and s_row[5] else None,
                } if s_row else None,
                "entrances": [
                    {
                        "cluster_size": e[0],
                        "confidence": float(e[1]),
                        "side": e[2],
                        "avg_dwell_sec": float(e[3]) if e[3] else None,
                        "stddev_position": float(e[4]) if e[4] else None,
                    }
                    for e in entrances
                ],
            }


def run_rubric_batch(pipeline_run_id: str) -> None:
    """Interactive batch grading: iterate golden buildings, print evidence, prompt for scores."""
    golden = list_golden_buildings()

    if not golden:
        print("No golden buildings. Use: golden-add --building-ids <id> --reason <reason>")
        return

    print(f"\nBatch Rubric Scoring")
    print(f"Pipeline Run: {pipeline_run_id}")
    print(f"Golden Buildings: {len(golden)}")
    print("=" * 70)
    print("Rate each on 0-3 scale:")
    print("  0 = bad,  1 = weak,  2 = plausible,  3 = strong")
    print("=" * 70)

    scored = 0
    skipped = 0

    for b in golden:
        bid = b["building_id"]
        print(f"\n[{scored + skipped + 1}/{len(golden)}] Building {bid} — {b['name'] or 'unnamed'}")
        print(f"  Type: {b['building_type']}, Stops: {b['stop_count']}")

        evidence = get_building_evidence_for_rubric(bid, pipeline_run_id)
        if evidence["score"]:
            print(f"  Difficulty: {evidence['score']['difficulty']:.2f} | Sample: {evidence['score']['sample_size']}")
            print(f"  Entrances: {len(evidence['entrances'])} candidates (avg conf: {sum(e['confidence'] for e in evidence['entrances']) / len(evidence['entrances']) if evidence['entrances'] else 0:.2f})")
        else:
            print(f"  No score data (clustering may not have run)")

        # Prompt for scores
        try:
            assign_raw = input("  Assignment quality (0-3)? ").strip()
            if not assign_raw:
                skipped += 1
                continue
            assign = int(assign_raw)

            entrance_raw = input("  Entrance plausibility (0-3)? ").strip()
            if not entrance_raw:
                skipped += 1
                continue
            entrance = int(entrance_raw)

            score_raw = input("  Score usefulness (0-3)? ").strip()
            if not score_raw:
                skipped += 1
                continue
            score = int(score_raw)

            note = input("  Note (optional)? ").strip() or None

            upsert_rubric(bid, pipeline_run_id, assign, entrance, score, note)
            print(f"  ✓ Saved")
            scored += 1

        except (ValueError, KeyboardInterrupt) as e:
            print(f"  Skipped: {e}")
            skipped += 1

    print("\n" + "=" * 70)
    print(f"Scored: {scored}, Skipped: {skipped}")

    summary = get_rubric_summary(pipeline_run_id)
    if summary["count"] > 0:
        print(f"\nRubric Summary ({summary['count']} buildings):")
        print(f"  Avg Assignment Quality: {summary['avg_assignment_quality']:.2f}")
        print(f"  Avg Entrance Plausibility: {summary['avg_entrance_plausibility']:.2f}")
        print(f"  Avg Score Usefulness: {summary['avg_score_usefulness']:.2f}")
