import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

# Manhattan bounding box (west, south, east, north)
MANHATTAN_BBOX = (-74.02, 40.70, -73.93, 40.88)

# DBSCAN parameters
DBSCAN_EPS_METERS = 5
DBSCAN_MIN_SAMPLES = 3

# Building assignment threshold in meters
BUILDING_ASSIGN_DISTANCE_M = 50

# Minimum stops per building to attempt clustering
MIN_STOPS_FOR_CLUSTERING = 5

# Score weights
SCORE_WEIGHTS = {
    "stop_variance": 0.25,
    "road_distance": 0.25,
    "entrance_count": 0.25,
    "dwell_time": 0.25,
}
