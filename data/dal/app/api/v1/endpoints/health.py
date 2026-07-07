"""Health check endpoints."""

from __future__ import annotations
import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.metadata_session import get_metadata_session
from app.db.operational_session import get_operational_session

router = APIRouter(tags=["Health"])


@router.get(
    "/health/live",
    summary="Liveness probe",
    description="Returns 200 if the service process is running.",
    response_model=dict,
)
@limiter.limit(
    f"{get_settings().default_rate_limit_per_minute}/minute"
)
async def liveness(request: Request):
    """Simple liveness check — the process is alive."""
    return {"status": "ok"}


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Verifies connectivity to metadata DB, operational DB, and Redis.",
    response_model=dict,
)
@limiter.limit(
    f"{get_settings().default_rate_limit_per_minute}/minute"
)
async def readiness(
    request: Request,
    meta_session: AsyncSession = Depends(get_metadata_session),
    ops_session: AsyncSession = Depends(get_operational_session),
):
    """Check all downstream dependencies are reachable."""
    checks: dict[str, str] = {}

    # Metadata DB
    try:
        await meta_session.execute(text("SELECT 1"))
        checks["metadata_db"] = "ok"
    except Exception as exc:
        checks["metadata_db"] = f"error: {str(exc)[:100]}"

    # Operational DB
    try:
        await ops_session.execute(text("SELECT 1"))
        checks["operational_db"] = "ok"
    except Exception as exc:
        checks["operational_db"] = f"error: {str(exc)[:100]}"

    # Redis
    try:
        redis = await get_redis()
        maybe = redis.ping()
        if asyncio.iscoroutine(maybe):
            pong = await maybe
        else:
            pong = maybe
        checks["redis"] = "ok" if pong else "error: ping failed"
    except Exception as exc:
        checks["redis"] = f"error: {str(exc)[:100]}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    from fastapi.responses import JSONResponse

    return JSONResponse(
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
        status_code=status_code,
    )
