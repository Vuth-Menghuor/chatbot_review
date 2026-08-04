import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.redis import redis_client

router = APIRouter(tags=["health"])


# Keep dependency checks in one helper so /health and /health/ready cannot drift apart.
async def dependency_statuses() -> dict[str, str]:
    dependencies = {"postgres": "up", "redis": "up", "orchestrator": "up"}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        dependencies["postgres"] = "down"
    try:
        await redis_client.ping()
    except Exception:
        dependencies["redis"] = "down"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.main_service_url}/health")
            response.raise_for_status()
    except Exception:
        dependencies["orchestrator"] = "down"
    return dependencies


# Liveness is intentionally process-only; dependency outages should not restart the API process.
@router.get("/health/live")
async def live():
    return {"status": "ok"}


# Readiness checks critical dependencies and tells orchestrators whether this instance can serve traffic.
@router.get("/health/ready")
async def ready(response: Response):
    dependencies = await dependency_statuses()
    is_ready = all(value == "up" for value in dependencies.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if is_ready else "not_ready", "dependencies": dependencies}


# Backward-compatible legacy endpoint for existing scripts while callers migrate to /live and /ready.
@router.get("/health")
async def health():
    dependencies = await dependency_statuses()
    result = {
        "status": "ok",
        "database": "ok" if dependencies["postgres"] == "up" else "unavailable",
        "redis": "ok" if dependencies["redis"] == "up" else "unavailable",
        "main_chatbot_service": "ok" if dependencies["orchestrator"] == "up" else "unavailable",
    }
    if any(value == "unavailable" for value in result.values()):
        result["status"] = "degraded"
    return result
