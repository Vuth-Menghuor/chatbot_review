"""Cache service — Redis-based query result caching."""

from __future__ import annotations

import json

from alembic.environment import Any

from app.core.cache import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_cached(cache_key: str) -> list[dict] | None:
    """
    Retrieve cached query results from Redis.

    Returns None on cache miss or error.
    """
    try:
        redis = await get_redis()
        raw = await redis.get(cache_key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Cache read failed", extra={"cache_key": cache_key[:32]})
        return None


async def set_cached(cache_key: str, data: list[dict], ttl_seconds: int) -> None:
    """Store query results in Redis with a TTL."""
    try:
        redis = await get_redis()
        serialized = json.dumps(data, default=str)
        await redis.setex(cache_key, ttl_seconds, serialized)
    except Exception:
        logger.warning("Cache write failed", extra={"cache_key": cache_key[:32]})


async def get_dict_cached(cache_key: str) -> dict[str, Any] | None:
    """
    Retrieve cached query results from Redis.

    Returns None on cache miss or error.
    """
    try:
        redis = await get_redis()
        raw = await redis.get(cache_key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Cache read failed", extra={"cache_key": cache_key[:32]})
        return None


async def set_dict_cached(cache_key: str, data: dict[str, Any], ttl_seconds: int) -> None:
    """Store query results in Redis with a TTL."""
    try:
        redis = await get_redis()
        serialized = json.dumps(data, default=str)
        await redis.setex(cache_key, ttl_seconds, serialized)
    except Exception:
        logger.warning("Cache write failed", extra={"cache_key": cache_key[:32]})