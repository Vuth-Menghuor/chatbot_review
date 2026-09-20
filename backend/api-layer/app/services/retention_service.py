"""Scheduled data-retention cleanup for records owned by the API layer."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import AuditLog, ChatThread, FileRecord
from app.services import minio_service

logger = logging.getLogger(__name__)


async def purge_expired_records(now: datetime | None = None) -> dict[str, int]:
    """Permanently remove API-layer data that has passed its configured retention period."""
    now = now or datetime.now(timezone.utc)
    active_chat_cutoff = now - timedelta(days=settings.chat_retention_days)
    deleted_chat_cutoff = now - timedelta(days=settings.deleted_chat_retention_days)
    deleted_file_cutoff = now - timedelta(days=settings.deleted_file_retention_days)
    audit_log_cutoff = now - timedelta(days=settings.audit_log_retention_days)

    async with SessionLocal() as db:
        expired_files = (
            await db.execute(
                select(FileRecord).where(
                    FileRecord.status == "deleted",
                    FileRecord.deleted_at.is_not(None),
                    FileRecord.deleted_at <= deleted_file_cutoff,
                )
            )
        ).scalars().all()
        for file_record in expired_files:
            await asyncio.to_thread(minio_service.delete_file, file_record.object_key)
            await db.delete(file_record)

        deleted_chats = await db.execute(
            delete(ChatThread).where(
                ChatThread.status == "deleted",
                ChatThread.updated_at <= deleted_chat_cutoff,
            )
        )
        inactive_chats = await db.execute(
            delete(ChatThread).where(
                ChatThread.status != "deleted",
                func.coalesce(ChatThread.last_activity_at, ChatThread.updated_at, ChatThread.created_at)
                <= active_chat_cutoff,
            )
        )
        audit_logs = await db.execute(delete(AuditLog).where(AuditLog.created_at <= audit_log_cutoff))
        await db.commit()

    result = {
        "files": len(expired_files),
        "deleted_chats": deleted_chats.rowcount or 0,
        "inactive_chats": inactive_chats.rowcount or 0,
        "audit_logs": audit_logs.rowcount or 0,
    }
    logger.info("Retention cleanup completed: %s", result)
    return result


async def retention_cleanup_loop() -> None:
    """Run once at startup and then at the configured interval until cancellation."""
    while True:
        try:
            await purge_expired_records()
        except Exception:
            logger.exception("Retention cleanup failed")
        await asyncio.sleep(settings.retention_cleanup_interval_seconds)
