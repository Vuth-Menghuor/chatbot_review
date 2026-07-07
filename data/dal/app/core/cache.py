"""Redis connection factory."""

from redis.asyncio import Redis

from app.core.config import get_settings

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return the shared async Redis client, creating it on first use."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    return _redis_client


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
