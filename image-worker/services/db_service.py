import logging
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def get_engine() -> Engine:
    return create_engine(_database_url(), pool_pre_ping=True)


def mark_job_completed(job_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE file_jobs
                SET status = 'completed', completed_at = :completed_at, error_message = NULL
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id, "completed_at": datetime.now(timezone.utc)},
        )


def mark_job_failed(job_id: str, error_message: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE file_jobs
                SET status = 'failed', completed_at = :completed_at, error_message = :error_message
                WHERE id = :job_id
                """
            ),
            {
                "job_id": job_id,
                "completed_at": datetime.now(timezone.utc),
                "error_message": error_message[:2000],
            },
        )


def mark_file_processed(file_id: str, public_url: str | None = None) -> None:
    params = {
        "file_id": file_id,
        "updated_at": datetime.now(timezone.utc),
        "status": "processed",
    }
    query = """
        UPDATE files
        SET status = :status, updated_at = :updated_at
    """
    if public_url:
        query += ", public_url = :public_url"
        params["public_url"] = public_url
    query += " WHERE id = :file_id"

    with get_engine().begin() as conn:
        conn.execute(text(query), params)


def file_exists(file_id: str) -> bool:
    with get_engine().connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM files WHERE id = :file_id AND deleted_at IS NULL"),
            {"file_id": file_id},
        )
        return result.scalar_one_or_none() is not None
