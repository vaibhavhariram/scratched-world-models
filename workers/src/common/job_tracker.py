"""
Pipeline job tracking for idempotency and observability.

Every pipeline run creates a job record. Stats are accumulated
during execution and persisted on completion.
"""

import json
import uuid
from datetime import datetime, timezone
from src.common.db import get_connection, get_cursor


def create_job(job_type: str, params: dict | None = None) -> str:
    """Create a new pipeline job and return its UUID."""
    job_id = str(uuid.uuid4())
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO logistics.pipeline_jobs (id, job_type, status, params)
                VALUES (%s, %s, 'pending', %s)
                """,
                (job_id, job_type, json.dumps(params) if params else None),
            )
        conn.commit()
    return job_id


def mark_running(job_id: str) -> None:
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                UPDATE logistics.pipeline_jobs
                SET status = 'running', started_at = %s
                WHERE id = %s
                """,
                (datetime.now(timezone.utc), job_id),
            )
        conn.commit()


def mark_completed(job_id: str, stats: dict | None = None) -> None:
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                UPDATE logistics.pipeline_jobs
                SET status = 'completed', completed_at = %s, stats = %s
                WHERE id = %s
                """,
                (
                    datetime.now(timezone.utc),
                    json.dumps(stats) if stats else None,
                    job_id,
                ),
            )
        conn.commit()


def mark_failed(job_id: str, error: str) -> None:
    with get_connection() as conn:
        with get_cursor(conn) as cur:
            cur.execute(
                """
                UPDATE logistics.pipeline_jobs
                SET status = 'failed', completed_at = %s, error = %s
                WHERE id = %s
                """,
                (datetime.now(timezone.utc), error[:4000], job_id),
            )
        conn.commit()
