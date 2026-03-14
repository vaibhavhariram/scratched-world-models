"""
Pipeline worker entry point.

Usage:
    python -m src.main ingest-buildings
    python -m src.main ingest-stops --year 2015 --month 1
    python -m src.main assign --batch-id <uuid>
    python -m src.main cluster
    python -m src.main score
"""

import argparse
import sys

import sentry_sdk

from src.common.config import SENTRY_DSN
from src.common.job_tracker import create_job, mark_running, mark_completed, mark_failed

if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN)


def main():
    parser = argparse.ArgumentParser(description="Logistics World Graph pipeline worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ingest-buildings
    subparsers.add_parser("ingest-buildings", help="Ingest Manhattan building footprints from OSM")

    # ingest-stops
    stops_parser = subparsers.add_parser("ingest-stops", help="Ingest NYC TLC taxi stop events")
    stops_parser.add_argument("--year", type=int, required=True)
    stops_parser.add_argument("--month", type=int, required=True)

    # assign
    assign_parser = subparsers.add_parser("assign", help="Assign stop events to nearest buildings")
    assign_parser.add_argument("--batch-id", type=str, required=True)

    # cluster
    subparsers.add_parser("cluster", help="Run DBSCAN clustering to find entrance candidates")

    # score
    subparsers.add_parser("score", help="Compute delivery difficulty scores")

    args = parser.parse_args()

    job_type = "ingest" if args.command.startswith("ingest") else args.command
    params = vars(args).copy()
    params.pop("command")

    job_id = create_job(job_type, params if params else None)

    try:
        mark_running(job_id)

        if args.command == "ingest-buildings":
            from src.ingest.buildings import run_ingest_buildings
            stats = run_ingest_buildings(job_id)

        elif args.command == "ingest-stops":
            from src.ingest.stops import run_ingest_stops
            stats = run_ingest_stops(job_id, args.year, args.month)

        elif args.command == "assign":
            from src.ingest.stops import run_assign_stops
            stats = run_assign_stops(job_id, args.batch_id)

        elif args.command == "cluster":
            from src.cluster.dbscan import run_clustering
            stats = run_clustering(job_id)

        elif args.command == "score":
            from src.score.compute import run_scoring
            stats = run_scoring(job_id)

        mark_completed(job_id, stats)
        print(f"Job {job_id} completed: {stats}")

    except Exception as e:
        mark_failed(job_id, str(e))
        if SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        print(f"Job {job_id} failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
