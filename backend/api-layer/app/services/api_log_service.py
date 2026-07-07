import logging
from uuid import UUID

from app.core.database import SessionLocal
from app.models import ApiRequestLog, RateLimitLog

logger = logging.getLogger(__name__)


async def save_api_request_log(
    *,
    user_id: UUID | None,
    method: str,
    path: str,
    query_string: str | None,
    status_code: int,
    ip_address: str | None,
    user_agent: str | None,
    duration_ms: int | None,
    request_id: str | None,
    error_detail: str | None,
) -> None:
    try:
        async with SessionLocal() as db:
            db.add(
                ApiRequestLog(
                    user_id=user_id,
                    method=method,
                    path=path,
                    query_string=query_string,
                    status_code=status_code,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    error_detail=error_detail,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to persist api_request_log for %s %s", method, path)


async def save_rate_limit_log(
    *,
    user_id: UUID | None,
    ip_address: str | None,
    limit_key: str,
    path: str | None,
    method: str | None,
    request_count: int,
    limit_value: int,
    window_seconds: int,
    blocked: bool = True,
) -> None:
    try:
        async with SessionLocal() as db:
            db.add(
                RateLimitLog(
                    user_id=user_id,
                    ip_address=ip_address,
                    limit_key=limit_key,
                    path=path,
                    method=method,
                    request_count=request_count,
                    limit_value=limit_value,
                    window_seconds=window_seconds,
                    blocked=blocked,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to persist rate_limit log for key %s", limit_key)
