from uuid import UUID

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import redis_client
from app.services.api_log_service import save_rate_limit_log


async def enforce_rate_limit(
    key: str,
    limit: int,
    window_seconds: int = 60,
    *,
    request: Request | None = None,
    user_id: UUID | None = None,
) -> None:
    redis_key = f"rate_limit:{key}"
    count = 0
    try:
        count = await redis_client.incr(redis_key)
        if count == 1:
            await redis_client.expire(redis_key, window_seconds)
    except Exception:
        return

    if count <= limit:
        return

    ip_address = request.client.host if request and request.client else None
    path = request.url.path if request else None
    method = request.method if request else None
    resolved_user_id = user_id or getattr(getattr(request, "state", None), "user_id", None)

    await save_rate_limit_log(
        user_id=resolved_user_id if isinstance(resolved_user_id, UUID) else None,
        ip_address=ip_address,
        limit_key=key,
        path=path,
        method=method,
        request_count=count,
        limit_value=limit,
        window_seconds=window_seconds,
        blocked=True,
    )

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please try again later.",
    )


async def check_general_rate_limit(request: Request) -> None:
    identity = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        f"general:{identity}",
        settings.general_rate_limit_requests,
        settings.rate_limit_window_seconds,
        request=request,
    )
