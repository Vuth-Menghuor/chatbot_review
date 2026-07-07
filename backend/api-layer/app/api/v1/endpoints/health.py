import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.redis import redis_client

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    result = {"status": "ok", "database": "ok", "redis": "ok", "main_chatbot_service": "ok"}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        result["database"] = "unavailable"
    try:
        await redis_client.ping()
    except Exception:
        result["redis"] = "unavailable"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.main_service_url}/health")
            response.raise_for_status()
    except Exception:
        result["main_chatbot_service"] = "unavailable"
    if any(value == "unavailable" for value in result.values()):
        result["status"] = "degraded"
    return result
