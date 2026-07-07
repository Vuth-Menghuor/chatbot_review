"""Audit logging service — persist audit records to the metadata DB."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AuditLog

logger = get_logger(__name__)


async def write_audit_log(
    session: AsyncSession,
    *,
    request_id: str,
    client_id: str | None = None,
    dataset: str | None = None,
    dataset_version: str | None = None,
    status_code: int,
    latency_ms: float | None = None,
    cache_hit: bool | None = None,
    query_fingerprint: str | None = None,
    error_summary: str | None = None,
    request_params: dict | None = None,
) -> None:
    """Insert an audit log record."""
    try:
        record = AuditLog(
            id=uuid.uuid4(),
            request_id=uuid.UUID(request_id),
            client_id=client_id,
            dataset=dataset,
            dataset_version=dataset_version,
            status_code=status_code,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            query_fingerprint=query_fingerprint,
            error_summary=error_summary,
            request_params=request_params,
            requested_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.commit()
    except Exception:
        logger.exception("Failed to write audit log", extra={"request_id": request_id})
        await session.rollback()
