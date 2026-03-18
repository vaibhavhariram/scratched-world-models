"""
Pipeline worker CLI with dev workflow support.

Usage examples:
    # Full pipeline
    python -m src.main ingest-buildings
    python -m src.main ingest-stops --year 2015 --month 1
    python -m src.main assign --batch-id <uuid>
    python -m src.main cluster
    python -m src.main score

    # Dev workflow: small slice with custom params
    python -m src.main ingest-stops --year 2015 --month 1 --row-limit 10000
    python -m src.main assign --batch-id <uuid> --assignment-radius 30
    python -m src.main cluster --eps 8 --min-samples 5 --building-id 42
    python -m src.main score --building-id 42

    # Dry run (compute without writing)
    python -m src.main cluster --dry-run

    # Targeted rerun
    python -m src.main cluster --building-id 42
    python -m src.main cluster --bbox=-74.01,40.71,-73.97,40.75
    python -m src.main cluster --rerun-pipeline <uuid>
    python -m src.main score --rerun-pipeline <uuid>
"""

import argparse
import sys

import sentry_sdk

from src.common.config import PipelineConfig, SENTRY_DSN
from src.common.job_tracker import create_job, mark_running, mark_completed, mark_failed

if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared flags for dev workflow."""
    parser.add_argument("--dry-run", action="store_true", help="Compute without writing to DB")
    parser.add_argument("--row-limit", type=int, default=None, help="Limit rows for dev testing")


def _add_tuning_args(parser: argparse.ArgumentParser) -> None:
    """Add pipeline parameter overrides."""
    parser.add_argument("--eps", type=float, default=None, help="DBSCAN eps in meters")
    parser.add_argument("--min-samples", type=int, default=None, help="DBSCAN min_samples")
    parser.add_argument("--min-building-samples", type=int, default=None, help="Min stops per building")
    parser.add_argument("--assignment-radius", type=float, default=None, help="Assignment radius in meters")


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    """Add targeted rerun flags."""
    parser.add_argument("--building-id", type=int, default=None, help="Target a single building")
    parser.add_argument("--bbox", type=str, default=None, help="Target bbox: west,south,east,north")
    parser.add_argument("--rerun-pipeline", type=str, default=None, help="Re-run from a previous pipeline run ID")


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    """Build PipelineConfig from CLI args, applying overrides."""
    cfg = PipelineConfig()
    if getattr(args, "dry_run", False):
        cfg.dry_run = True
    if getattr(args, "row_limit", None):
        cfg.row_limit = args.row_limit
    if getattr(args, "eps", None):
        cfg.dbscan_eps_m = args.eps
    if getattr(args, "min_samples", None):
        cfg.dbscan_min_samples = args.min_samples
    if getattr(args, "min_building_samples", None):
        cfg.min_building_samples = args.min_building_samples
    if getattr(args, "assignment_radius", None):
        cfg.assignment_radius_m = args.assignment_radius
    return cfg


def _parse_bbox(bbox_str: str | None) -> tuple[float, float, float, float] | None:
    if not bbox_str:
        return None
    parts = [float(x) for x in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 4 comma-separated floats: west,south,east,north")
    return tuple(parts)


def main():
    parser = argparse.ArgumentParser(description="Logistics World Graph pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ingest-buildings
    p_bld = subparsers.add_parser("ingest-buildings", help="Ingest OSM building footprints")
    _add_common_args(p_bld)

    # ingest-stops
    p_stops = subparsers.add_parser("ingest-stops", help="Ingest NYC TLC taxi stops")
    p_stops.add_argument("--year", type=int, required=True)
    p_stops.add_argument("--month", type=int, required=True)
    _add_common_args(p_stops)

    # assign
    p_assign = subparsers.add_parser("assign", help="Assign stops to buildings")
    p_assign.add_argument("--batch-id", type=str, required=True)
    _add_common_args(p_assign)
    _add_tuning_args(p_assign)

    # cluster
    p_cluster = subparsers.add_parser("cluster", help="DBSCAN clustering")
    _add_common_args(p_cluster)
    _add_tuning_args(p_cluster)
    _add_target_args(p_cluster)

    # score
    p_score = subparsers.add_parser("score", help="Compute difficulty scores")
    _add_common_args(p_score)
    _add_target_args(p_score)

    # Validation tooling commands (no job tracking)

    # golden-add
    p_gadd = subparsers.add_parser("golden-add", help="Add buildings to golden validation set")
    p_gadd.add_argument("--building-ids", type=str, required=True, help="Comma-separated building IDs")
    p_gadd.add_argument("--reason", type=str, default=None, help="Why this building was selected")

    # golden-remove
    p_grm = subparsers.add_parser("golden-remove", help="Remove buildings from golden set")
    p_grm.add_argument("--building-ids", type=str, required=True, help="Comma-separated building IDs")

    # golden-list
    p_gls = subparsers.add_parser("golden-list", help="List all golden buildings")

    # sanity-check
    p_san = subparsers.add_parser("sanity-check", help="Run data quality checks")
    p_san.add_argument("--building-id", type=int, default=None, help="Check a single building")

    # rubric
    p_rubric = subparsers.add_parser("rubric", help="Score a building with rubric")
    p_rubric.add_argument("--pipeline-run-id", type=str, required=True, help="Pipeline run UUID")
    p_rubric.add_argument("--building-id", type=int, required=True, help="Building ID")
    p_rubric.add_argument("--assignment", type=int, required=True, choices=[0, 1, 2, 3], help="Assignment quality (0-3)")
    p_rubric.add_argument("--entrance", type=int, required=True, choices=[0, 1, 2, 3], help="Entrance plausibility (0-3)")
    p_rubric.add_argument("--score", type=int, required=True, choices=[0, 1, 2, 3], help="Score usefulness (0-3)")
    p_rubric.add_argument("--note", type=str, default=None, help="Optional note")

    # rubric-batch
    p_rbatch = subparsers.add_parser("rubric-batch", help="Interactive batch rubric scoring")
    p_rbatch.add_argument("--pipeline-run-id", type=str, required=True, help="Pipeline run UUID")

    # sweep
    p_sweep = subparsers.add_parser("sweep", help="Parameter sweep: test multiple clustering params")
    p_sweep.add_argument("--eps", type=str, required=True, help="Comma-separated eps values (meters)")
    p_sweep.add_argument("--min-samples", type=str, default="3", help="Comma-separated min_samples values")
    p_sweep.add_argument("--tag", type=str, required=True, help="Tag for grouping sweep runs")
    _add_common_args(p_sweep)

    # compare
    p_cmp = subparsers.add_parser("compare", help="Compare pipeline runs")
    p_cmp.add_argument("--run-ids", type=str, default=None, help="Comma-separated run UUIDs")
    p_cmp.add_argument("--tag", type=str, default=None, help="Compare all runs with this sweep tag")

    args = parser.parse_args()
    cfg = _build_config(args)

    # Validation tooling commands: no job tracking
    if args.command == "golden-add":
        from src.validate.golden import add_golden_buildings
        building_ids = [int(x.strip()) for x in args.building_ids.split(",")]
        count = add_golden_buildings(building_ids, args.reason)
        print(f"Added {count} golden buildings")
        return

    elif args.command == "golden-remove":
        from src.validate.golden import remove_golden_buildings
        building_ids = [int(x.strip()) for x in args.building_ids.split(",")]
        count = remove_golden_buildings(building_ids)
        print(f"Removed {count} golden buildings")
        return

    elif args.command == "golden-list":
        from src.validate.golden import print_golden_list
        print_golden_list()
        return

    elif args.command == "sanity-check":
        from src.validate.sanity import run_sanity_check
        run_sanity_check([args.building_id] if args.building_id else None)
        return

    elif args.command == "rubric":
        from src.validate.rubric import upsert_rubric
        upsert_rubric(args.building_id, args.pipeline_run_id, args.assignment, args.entrance, args.score, args.note)
        print(f"Saved rubric scores for building {args.building_id}")
        return

    elif args.command == "rubric-batch":
        from src.validate.rubric import run_rubric_batch
        run_rubric_batch(args.pipeline_run_id)
        return

    elif args.command == "sweep":
        from src.validate.sweep import run_sweep
        eps_values = [float(x.strip()) for x in args.eps.split(",")]
        min_samples_values = [int(x.strip()) for x in args.min_samples.split(",")]
        run_sweep(eps_values, min_samples_values, args.tag, cfg)
        return

    elif args.command == "compare":
        from src.validate.compare import compare_runs
        run_ids = None
        if args.run_ids:
            run_ids = [x.strip() for x in args.run_ids.split(",")]
        compare_runs(run_ids, args.tag)
        return

    # Pipeline commands: create job and track
    job_type_map = {
        "ingest-buildings": "ingest",
        "ingest-stops": "ingest",
        "assign": "assign",
        "cluster": "cluster",
        "score": "score",
    }
    job_type = job_type_map[args.command]

    # Build params for job record
    params = cfg.to_dict()
    params["command"] = args.command
    if hasattr(args, "year"):
        params["year"] = args.year
        params["month"] = args.month
    if hasattr(args, "batch_id"):
        params["batch_id"] = args.batch_id
    if getattr(args, "building_id", None):
        params["target_building_id"] = args.building_id
    if getattr(args, "bbox", None):
        params["target_bbox"] = args.bbox
    if getattr(args, "rerun_pipeline", None):
        params["rerun_pipeline_id"] = args.rerun_pipeline

    job_id = create_job(job_type, params)
    print(f"Job {job_id} created ({args.command})")

    if cfg.dry_run:
        print("[DRY RUN MODE]")

    try:
        mark_running(job_id)

        if args.command == "ingest-buildings":
            from src.ingest.buildings import run_ingest_buildings
            stats = run_ingest_buildings(job_id, cfg)

        elif args.command == "ingest-stops":
            from src.ingest.stops import run_ingest_stops
            stats = run_ingest_stops(job_id, args.year, args.month, cfg)

        elif args.command == "assign":
            from src.ingest.stops import run_assign_stops
            stats = run_assign_stops(job_id, args.batch_id, cfg)

        elif args.command == "cluster":
            from src.cluster.dbscan import run_clustering
            target_bbox = _parse_bbox(getattr(args, "bbox", None))
            stats = run_clustering(
                job_id, cfg,
                building_id=args.building_id,
                target_bbox=target_bbox,
                rerun_pipeline_id=args.rerun_pipeline,
            )

        elif args.command == "score":
            from src.score.compute import run_scoring
            target_bbox = _parse_bbox(getattr(args, "bbox", None))
            stats = run_scoring(
                job_id, cfg,
                building_id=args.building_id,
                target_bbox=target_bbox,
                rerun_pipeline_id=args.rerun_pipeline,
            )

        mark_completed(job_id, stats)
        print(f"\nJob {job_id} completed")

    except Exception as e:
        mark_failed(job_id, str(e))
        if SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        print(f"Job {job_id} failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
