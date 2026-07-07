"""
Redis cache client for the general retrieval service.
Fails open: if Redis is unavailable, callers get cache misses, not errors.
"""

import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class CacheClient:
    def __init__(self, host: str, port: int, enabled: bool = True):
        self.enabled = enabled and redis is not None
        self._client = None
        if self.enabled:
            try:
                self._client = redis.Redis(
                    host=host,
                    port=port,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
            except Exception as exc:
                logger.warning(f"Redis init failed, caching disabled: {exc}")
                self.enabled = False

    @staticmethod
    def make_key(prefix: str, *parts: str) -> str:
        raw = "|".join(parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}:{digest}"

    async def get_json(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            value = await self._client.get(key)
            return json.loads(value) if value else None
        except Exception as exc:
            logger.debug(f"Cache get failed for {key}: {exc}")
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        if not self.enabled:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl)
        except Exception as exc:
            logger.debug(f"Cache set failed for {key}: {exc}")

    async def health(self) -> dict:
        if not self.enabled:
            return {"status": "disabled"}
        try:
            await self._client.ping()
            return {"status": "healthy"}
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}