"""
Redis Cache Client — Retrieval Service.

Provides an asynchronous, fail-open cache layer backed by Redis. The
primary use case is cross-process sharing of the HS-code corpus so that
multiple Uvicorn workers don't each scroll the full Qdrant collection.

Design Principles
-----------------
- **Fail-open**: if Redis is unreachable at startup or at call time, cache
  operations return misses (``None``) rather than raising exceptions.
- **Async-first**: uses ``redis.asyncio`` so cache I/O never blocks the
  event loop.
- **Minimal surface**: only ``get_json`` / ``set_json`` are exposed, plus
  a ``health()`` check for observability.

Cache Key Strategy
------------------
Keys are constructed as ``{prefix}:{sha256[:24]}`` to avoid collisions
while keeping keys human-traceable in Redis inspection tools.
"""

import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Graceful degradation if ``redis`` is not installed.
try:
    import redis.asyncio as redis
except ImportError:
    redis = None


class CacheClient:
    """
    Async Redis cache client with automatic fail-open behaviour.

    Parameters
    ----------
    host : str
        Redis server hostname.
    port : int
        Redis server port.
    enabled : bool
        When False (or when the ``redis`` package is not installed), all
        operations become no-ops that return ``None`` (cache miss).
    """

    def __init__(self, host: str, port: int, enabled: bool = True):
        self.enabled = enabled and redis is not None
        self._client = None
        if self.enabled:
            try:
                self._client = redis.Redis(
                    host=host,
                    port=port,
                    decode_responses=True,
                    socket_connect_timeout=2,  # fail fast on connect
                    socket_timeout=2,           # fail fast on operations
                )
            except Exception as exc:
                logger.warning("Redis init failed, caching disabled: %s", exc)
                self.enabled = False

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(prefix: str, *parts: str) -> str:
        """
        Build a deterministic, collision-resistant cache key.

        The key format is ``{prefix}:{sha256[:24]}`` where the hash is
        computed over all ``parts`` joined by ``|``.
        """
        raw = "|".join(parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}:{digest}"

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def get_json(self, key: str) -> Optional[Any]:
        """
        Retrieve a JSON-deserialised value from the cache.

        Returns ``None`` on cache miss, deserialisation failure, or if the
        cache is disabled / unreachable.
        """
        if not self.enabled:
            return None
        try:
            value = await self._client.get(key)
            return json.loads(value) if value else None
        except Exception as exc:
            logger.debug("Cache get failed for %s: %s", key, exc)
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        """
        Store a JSON-serialisable value in the cache with the given TTL
        (in seconds). Silently ignored if the cache is disabled.
        """
        if not self.enabled:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl)
        except Exception as exc:
            logger.debug("Cache set failed for %s: %s", key, exc)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict:
        """
        Check cache health.

        Returns ``{"status": "healthy"}`` if Redis responds to PING,
        ``{"status": "disabled"}`` if the cache was never enabled, or
        ``{"status": "unhealthy", "error": ...}`` on failure.
        """
        if not self.enabled:
            return {"status": "disabled"}
        try:
            await self._client.ping()
            return {"status": "healthy"}
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}