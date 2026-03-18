"""Parameter sweep runner: test multiple combinations of clustering/scoring parameters."""

from itertools import product
from src.common.config import PipelineConfig
from src.common.job_tracker import create_job, mark_running, mark_completed, mark_failed
from src.cluster.dbscan import run_clustering
from src.score.compute import run_scoring


def run_sweep(
    eps_values: list[float],
    min_samples_values: list[int],
    tag: str,
    base_config: PipelineConfig,
) -> list[dict]:
    """
    Run cluster+score for each (eps, min_samples) combo.

    Args:
        eps_values: DBSCAN epsilon values in meters
        min_samples_values: DBSCAN minimum samples per cluster
        tag: human-readable tag for grouping sweep results (e.g., "march-tuning-v1")
        base_config: base PipelineConfig (copy and override eps/min_samples)

    Returns:
        list of {run_id, eps, min_samples, cluster_stats, score_stats}
    """
    results = []
    total_runs = len(eps_values) * len(min_samples_values)
    run_number = 0

    print(f"\nParameter Sweep: {tag}")
    print(f"eps values: {eps_values}")
    print(f"min_samples values: {min_samples_values}")
    print(f"Total runs: {total_runs}")
    print("=" * 70)

    for eps, ms in product(eps_values, min_samples_values):
        run_number += 1

        cfg = PipelineConfig(
            dbscan_eps_m=eps,
            dbscan_min_samples=ms,
            min_building_samples=base_config.min_building_samples,
            assignment_radius_m=base_config.assignment_radius_m,
            row_limit=base_config.row_limit,
            bbox=base_config.bbox,
            dry_run=base_config.dry_run,
        )

        params = cfg.to_dict()
        params["command"] = "sweep"
        params["sweep_tag"] = tag

        print(f"\n[{run_number}/{total_runs}] eps={eps}, min_samples={ms}")

        job_id = create_job("sweep", params)
        mark_running(job_id)

        try:
            print(f"  Job ID: {job_id}")
            print("  Running clustering...")
            cluster_stats = run_clustering(job_id, cfg)

            print("  Running scoring...")
            score_stats = run_scoring(job_id, cfg)

            combined_stats = {**cluster_stats, **score_stats}
            mark_completed(job_id, combined_stats)

            result = {
                "run_id": str(job_id),
                "eps": eps,
                "min_samples": ms,
                **combined_stats,
            }
            results.append(result)
            print(f"  ✓ Completed")

        except Exception as e:
            mark_failed(job_id, str(e))
            print(f"  ✗ FAILED: {e}")

    _print_sweep_summary(results, tag)
    return results


def _print_sweep_summary(results: list[dict], tag: str) -> None:
    """Print a summary table of sweep results."""
    if not results:
        print("\n" + "=" * 70)
        print("No sweep runs completed")
        return

    print("\n" + "=" * 70)
    print(f"Sweep Summary: {tag}")
    print("=" * 70)
    print(
        f"{'eps':<6} {'min_s':<7} {'clustered':<12} {'entrances':<12} "
        f"{'scored':<10} {'avg_diff':<12}"
    )
    print("-" * 70)

    for r in results:
        eps = r.get("eps", "-")
        ms = r.get("min_samples", "-")
        clustered = r.get("clustered_buildings", 0)
        entrances = r.get("entrance_candidates_created", 0)
        scored = r.get("scored_buildings", 0)
        avg_diff = r.get("difficulty_mean", 0)

        print(f"{eps:<6.1f} {ms:<7} {clustered:<12} {entrances:<12} {scored:<10} {avg_diff:<12.3f}")

    print("=" * 70)
    print(f"All results tagged with: {tag}")
    print(f"Compare with: compare --tag {tag}")
