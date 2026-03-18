"""Run comparison report: compare pipeline runs side by side."""

from src.common.db import get_connection, get_cursor


def compare_runs(
    run_ids: list[str] | None = None,
    tag: str | None = None,
) -> None:
    """
    Compare pipeline runs side by side.

    Args:
        run_ids: list of pipeline_run_id UUIDs to compare
        tag: if given, find all sweep runs with this tag and compare them
    """
    if not run_ids and not tag:
        print("Usage: compare --run-ids <uuid1>,<uuid2> OR --tag <tag_name>")
        return

    with get_connection() as conn:
        with get_cursor(conn) as cur:
            if tag:
                # Find all sweep runs with this tag
                cur.execute("""
                    SELECT id
                    FROM logistics.pipeline_jobs
                    WHERE job_type = 'sweep'
                      AND params->>'sweep_tag' = %s
                    ORDER BY created_at ASC
                """, (tag,))
                run_ids = [str(row[0]) for row in cur.fetchall()]
                if not run_ids:
                    print(f"No sweep runs found with tag: {tag}")
                    return

            if not run_ids:
                print("No runs to compare")
                return

            # Fetch run params and stats
            print("\n" + "=" * 100)
            print(f"Run Comparison: {tag if tag else 'Custom'}")
            print("=" * 100)

            run_params = _fetch_run_params(run_ids)
            _print_run_summary_table(run_params)

            # Fetch golden building comparison
            golden_data = _fetch_golden_comparison(run_ids)
            if golden_data:
                _print_golden_buildings_detail(golden_data)

            print("=" * 100)


def _fetch_run_params(run_ids: list[str]) -> list[dict]:
    """Get params and stats for each run from pipeline_jobs."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            runs = []
            for run_id in run_ids:
                cur.execute("""
                    SELECT
                        id::text,
                        params->>'dbscan_eps_m' as eps,
                        params->>'dbscan_min_samples' as min_samples,
                        stats->>'clustered_buildings' as clustered,
                        stats->>'entrance_candidates_created' as entrances,
                        stats->>'scored_buildings' as scored,
                        stats->>'difficulty_mean' as avg_difficulty
                    FROM logistics.pipeline_jobs
                    WHERE id::text = %s
                """, (run_id,))
                row = cur.fetchone()
                if row:
                    runs.append({
                        "id": row[0][:8],
                        "eps": float(row[1]) if row[1] else None,
                        "min_samples": int(row[2]) if row[2] else None,
                        "clustered": int(row[3]) if row[3] else None,
                        "entrances": int(row[4]) if row[4] else None,
                        "scored": int(row[5]) if row[5] else None,
                        "avg_difficulty": float(row[6]) if row[6] else None,
                    })
            return runs


def _fetch_golden_comparison(run_ids: list[str]) -> list[dict]:
    """For each golden building x run, fetch entrance count, confidence, score, rubric."""
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute("""
                SELECT
                    gb.building_id,
                    b.name,
                    ec.pipeline_run_id::text,
                    COUNT(ec.id) as entrance_count,
                    ROUND(AVG(ec.confidence)::numeric, 2) as avg_confidence,
                    ROUND(bs.difficulty::numeric, 2) as difficulty,
                    CONCAT(rs.assignment_quality, '/', rs.entrance_plausibility, '/', rs.score_usefulness)
                        as rubric_scores
                FROM logistics.golden_buildings gb
                JOIN logistics.buildings b ON b.id = gb.building_id
                LEFT JOIN logistics.entrance_candidates ec ON ec.building_id = gb.building_id
                    AND ec.pipeline_run_id::text = ANY(%s)
                LEFT JOIN logistics.building_scores bs ON bs.building_id = gb.building_id
                    AND bs.pipeline_run_id = ec.pipeline_run_id
                LEFT JOIN logistics.building_rubric_scores rs ON rs.building_id = gb.building_id
                    AND rs.pipeline_run_id = ec.pipeline_run_id
                GROUP BY gb.building_id, b.name, ec.pipeline_run_id, bs.difficulty, rs.assignment_quality,
                         rs.entrance_plausibility, rs.score_usefulness
                ORDER BY gb.building_id, ec.pipeline_run_id
            """, (run_ids,))

            return [
                {
                    "building_id": row[0],
                    "name": row[1],
                    "run_id": row[2][:8] if row[2] else None,
                    "entrance_count": row[3],
                    "avg_confidence": float(row[4]) if row[4] else None,
                    "difficulty": float(row[5]) if row[5] else None,
                    "rubric": row[6],
                }
                for row in cur.fetchall()
            ]


def _print_run_summary_table(runs: list[dict]) -> None:
    """Print run summary table."""
    print(f"\nRun Summary ({len(runs)} runs):")
    print("-" * 100)
    print(
        f"{'Run':<10} {'eps':<8} {'min_s':<8} {'clustered':<12} "
        f"{'entrances':<12} {'scored':<10} {'avg_diff':<12}"
    )
    print("-" * 100)

    for r in runs:
        eps = f"{r['eps']:.1f}" if r['eps'] is not None else "--"
        ms = str(r['min_samples']) if r['min_samples'] is not None else "--"
        clust = str(r['clustered']) if r['clustered'] is not None else "--"
        ent = str(r['entrances']) if r['entrances'] is not None else "--"
        scored = str(r['scored']) if r['scored'] is not None else "--"
        diff = f"{r['avg_difficulty']:.3f}" if r['avg_difficulty'] is not None else "--"

        print(f"{r['id']:<10} {eps:<8} {ms:<8} {clust:<12} {ent:<12} {scored:<10} {diff:<12}")

    print("-" * 100)


def _print_golden_buildings_detail(golden_data: list[dict]) -> None:
    """Print golden buildings detail for each run."""
    if not golden_data:
        return

    print(f"\nGolden Buildings Detail ({len(set(d['building_id'] for d in golden_data))} buildings):")
    print("-" * 100)

    current_bid = None
    for row in golden_data:
        if row["building_id"] != current_bid:
            current_bid = row["building_id"]
            print(f"Building {current_bid}: {row['name'] or 'unnamed'}")

        run_id = row["run_id"] or "--"
        ent_ct = row["entrance_count"] or 0
        conf = f"{row['avg_confidence']:.2f}" if row["avg_confidence"] is not None else "--"
        diff = f"{row['difficulty']:.2f}" if row["difficulty"] is not None else "--"
        rubric = row["rubric"] or "--"

        print(f"  {run_id:<8} entrances={ent_ct}, conf={conf}, diff={diff}, rubric={rubric}")

    print("-" * 100)
