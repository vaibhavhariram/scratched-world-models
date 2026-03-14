"""
Config-driven pipeline parameters.

All tunable parameters are centralized here. Values can be overridden
via CLI flags or environment variables for dev/prod flexibility.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# Manhattan bounding box (west, south, east, north)
MANHATTAN_BBOX = (-74.02, 40.70, -73.93, 40.88)


@dataclass
class PipelineConfig:
    """All tunable pipeline parameters in one place."""

    # Building assignment
    assignment_radius_m: float = 50.0

    # DBSCAN clustering
    dbscan_eps_m: float = 5.0
    dbscan_min_samples: int = 3

    # Minimum stops per building to attempt clustering
    min_building_samples: int = 5

    # Score weights (must sum to 1.0)
    score_weights: dict = field(default_factory=lambda: {
        "stop_variance": 0.25,
        "road_distance": 0.25,
        "entrance_count": 0.25,
        "dwell_time": 0.25,
    })

    # Dev workflow: optional row limit for ingestion
    row_limit: int | None = None

    # Dev workflow: optional bbox override (west, south, east, north)
    bbox: tuple[float, float, float, float] = MANHATTAN_BBOX

    # Dry-run mode: compute but don't write to DB
    dry_run: bool = False

    def to_dict(self) -> dict:
        """Serialize for storage in pipeline_jobs.params."""
        return {
            "assignment_radius_m": self.assignment_radius_m,
            "dbscan_eps_m": self.dbscan_eps_m,
            "dbscan_min_samples": self.dbscan_min_samples,
            "min_building_samples": self.min_building_samples,
            "row_limit": self.row_limit,
            "bbox": list(self.bbox),
            "dry_run": self.dry_run,
        }
