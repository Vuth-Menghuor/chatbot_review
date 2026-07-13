import json
import logging
import hashlib
import re
from datetime import datetime, time, timedelta
import redis

logger = logging.getLogger(__name__)

from app.core.config import get_settings


def normalize_question(question: str) -> str:
    """Normalize a user question by lowercasing, stripping, and collapsing spaces."""
    q = question.strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def get_cache_key(question: str) -> str:
    """Generate a clean SHA-256 Redis key from a normalized question."""
    normalized = normalize_question(question)
    sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"trade_cache:{sha}"


def get_seconds_until_midnight() -> int:
    """Calculate the number of seconds remaining until midnight local time (minimum 60s)."""
    now = datetime.now()  # Asia/Phnom_Penh local time (via TZ env var)
    tomorrow = now.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, time.min)
    ttl = int((next_midnight - now).total_seconds())
    return max(ttl, 60)


class CacheService:
    """Synchronous Redis cache manager with fail-open safety."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.enabled = self.settings.cache_enabled
        self.redis_client = None

        if not self.enabled:
            logger.info("Trade10 Cache is disabled via settings.")
            return

        try:
            logger.info(f"Initializing Trade10 Redis Client with URL: {self.settings.redis_url}")
            self.redis_client = redis.Redis.from_url(self.settings.redis_url, socket_timeout=3.0)
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}. Caching will fail open.", exc_info=True)
            self.redis_client = None

    def get(self, question: str) -> dict | None:
        """Retrieve cached response for a question. Fails open on any error."""
        if not self.enabled or not self.redis_client:
            return None

        key = get_cache_key(question)
        try:
            raw = self.redis_client.get(key)
            if not raw:
                logger.debug(f"Cache miss for question: '{question}' (Key: {key})")
                return None

            logger.info(f"Cache hit for question: '{question}' (Key: {key})")
            return json.loads(raw.decode("utf-8"))

        except Exception as e:
            logger.error(f"Redis cache GET error for key {key}: {e}. Failing open.", exc_info=True)
            return None

    def set(self, question: str, response: dict) -> bool:
        """Store response in cache with dynamic TTL. Fails open on any error."""
        if not self.enabled or not self.redis_client:
            return False

        key = get_cache_key(question)
        try:
            serialized = json.dumps(response)
            ttl = get_seconds_until_midnight()
            
            logger.info(f"Caching response for key {key} with TTL of {ttl} seconds (expires at midnight)")
            self.redis_client.setex(key, ttl, serialized)
            return True

        except Exception as e:
            logger.error(f"Redis cache SET error for key {key}: {e}. Failing open.", exc_info=True)
            return False
