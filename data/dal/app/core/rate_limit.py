"""SlowAPI-based rate limiter middleware.

Uses SlowAPI (built on top of limits library) to enforce per-client
rate limiting at the middleware level. Clients are identified by
the x-api-key header to prevent bulk access from the same client.
"""

from __future__ import annotations
from typing import (
    Callable,
    List,
    Union,
)

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def _get_client_key(request: Request) -> str:
    """
    Extract the client identity for rate limiting.

    Uses the x-api-key header so rate limits are tracked per API key.
    Falls back to client IP if no API key is provided (the auth layer
    will reject the request anyway, but this prevents unauthenticated
    flood attacks too).
    """
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key
    # Fallback to client IP
    return request.client.host if request.client else "unknown"


def _get_default_limits() -> List[Union[str, Callable[..., str]]]:
    """Build the default rate-limit string from settings."""
    return [f"{settings.default_rate_limit_per_minute}/minute"]


# --- SlowAPI Limiter instance ---
# The Limiter is created as a module-level singleton.
# default_limits applies to all routes unless overridden with @limiter.limit().
limiter = Limiter(
    key_func=_get_client_key,
    default_limits=_get_default_limits(),
    storage_uri=settings.redis_url,
    strategy="fixed-window",
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for SlowAPI rate limit errors.

    Returns the standard DAL error envelope so clients see a consistent
    error format instead of SlowAPI's default plain-text response.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    if not settings.is_production:
        logger.warning(
            "Rate limit exceeded",
            extra={
                "request_id": request_id,
                "client_key": _get_client_key(request),
                "detail": str(exc.detail),
            },
        )
    return JSONResponse(
        status_code=429,
        content={
            "request_id": request_id,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded. Try again later.",
            },
        },
        headers={"Retry-After": "60"},
    )
