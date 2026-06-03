"""
Cache Service - Response caching and TTL management
Handles caching of query results to improve performance
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json
# Generate hashed cache keys
import hashlib
import os
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class CacheLevel(str, Enum):
    """Cache levels."""
    MEMORY = "memory"
    REDIS = "redis"
    HYBRID = "hybrid"


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str #unique cache id
    value: Dict[str, Any] #actual response data
    created_at: datetime #timestamp of cache creation
    ttl_seconds: int #expiration time in seconds 
    hits: int = 0 #number of access 
    source: str = ""  # e.g., "retrieval", "calculator" where it come from
    
    @property
    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        elapsed = (datetime.utcnow() - self.created_at).total_seconds()
        return elapsed > self.ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "hits": self.hits,
            "source": self.source,
            "is_expired": self.is_expired,
        }


class MemoryCache:
    """In-memory cache implementation."""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize memory cache.
        
        Args:
            max_size: Maximum number of entries
        """
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size # by default it can store up to 1000 entries.
        logger.info(f"Memory cache initialized (max size: {max_size})")
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache.
        1. check if the key exists in cache
        2. if exists, check if the entry is expired
        3. if not expired, increment hits
        4. Return the value 
        """
        if key in self.cache:
            entry = self.cache[key]
            
            if entry.is_expired:
                del self.cache[key]
                logger.debug(f"Cache entry expired: {key}")
                return None
            
            entry.hits += 1
            logger.debug(f"Cache hit: {key} (hits: {entry.hits})")
            return entry.value
        
        return None
    
    # The cache will be expired base on ttl so in this case it will expired in 1 hour, and the expired entry will be removed when get or set new entry, or call cleanup_expired method
    def set(self, key: str, value: Dict[str, Any], ttl_seconds: int = 3600, source: str = "") -> bool:
        """Set value in cache."""
        try:
            if len(self.cache) >= self.max_size:
                # Remove least recently used entry, only if the cache is full.
                oldest_key = min(
                    self.cache.keys(),
                    key=lambda k: self.cache[k].created_at
                )
                del self.cache[oldest_key]
                logger.debug(f"Removed oldest cache entry: {oldest_key}")
            
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.utcnow(), # set creation time to now, which made this is not a LRU cache, but more like a FIFO / oldest-first eviction
                ttl_seconds=ttl_seconds,
                source=source,
            )
            self.cache[key] = entry
            logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s, source: {source})")
            return True
        except Exception as e:
            logger.error(f"Cache set failed: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Cache deleted: {key}")
            return True
        return False
    
    def clear(self):
        """Clear entire cache."""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def cleanup_expired(self):
        """Remove expired entries."""
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired
        ]
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
            
    #Return statistics about the cache, including size, max size, total hits, average hits per entry, and memory usage
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = sum(entry.hits for entry in self.cache.values())
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "total_hits": total_hits,
            "avg_hits_per_entry": total_hits / len(self.cache) if self.cache else 0,
            "memory_usage_mb": len(str(self.cache)) / (1024 * 1024),
        }


class RedisCache:
    """Redis cache implementation."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        """Initialize redis cache."""
        try:
            import redis
            self.client = redis.Redis(
                host=host, port=port, db=db, password=password, decode_responses=True
            )
            # Test connection
            self.client.ping()
            logger.info(f"Redis cache initialized (host: {host}:{port})")
            self.is_available = True
        except ImportError:
            logger.error("redis package not installed. Run: pip install redis")
            self.client = None
            self.is_available = False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None
            self.is_available = False
            
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value from cache."""
        if not self.is_available:
            return None
            
        try:
            #fetch serialized JSON.
            data = self.client.get(key)
            if data:
                entry = json.loads(data)
                
                # Try to increment hits safely (swallow error if it fails)
                try:
                    entry['hits'] = entry.get('hits', 0) + 1
                    # Note: We don't reset the TTL here to match memory cache behavior
                    # which keeps the original TTL
                except Exception:
                    pass
                
                logger.debug(f"Redis cache hit: {key}")
                return entry.get('value')
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            
        return None
        
    def set(self, key: str, value: Dict[str, Any], ttl_seconds: int = 3600, source: str = "") -> bool:
        """Set value in cache."""
        if not self.is_available:
            return False
            
        try:
            entry = {
                "key": key,
                "value": value,
                "created_at": datetime.utcnow().isoformat(),
                "ttl_seconds": ttl_seconds,
                "hits": 0,
                "source": source,
            }
            self.client.set(key, json.dumps(entry), ex=ttl_seconds) # JSON data become redis stores strings/bytes.
            logger.debug(f"Redis cache set: {key} (TTL: {ttl_seconds}s)")
            return True
        except Exception as e:
            logger.error(f"Redis set failed: {e}")
            return False
            
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not self.is_available:
            return False
            
        try:
            result = self.client.delete(key)
            if result > 0:
                logger.debug(f"Redis cache deleted: {key}")
                return True
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")
            
        return False
        
    def clear(self):
        """Clear entire cache."""
        if self.is_available:
            try:
                self.client.flushdb()
                logger.info("Redis cache cleared")
            except Exception as e:
                logger.warning(f"Redis flushdb error: {e}")
                
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.is_available:
            return {"status": "unavailable"}
            
        try:
            info = self.client.info()
            return {
                "size": self.client.dbsize(),
                "memory_usage_mb": float(info.get('used_memory', 0)) / (1024 * 1024),
                "hits": info.get('keyspace_hits', 0),
                "misses": info.get('keyspace_misses', 0),
            }
        except Exception as e:
            logger.warning(f"Redis get_stats error: {e}")
            return {"status": "error", "message": str(e)}


class CacheService:
    """
    Cache service for query results.
    Supports in-memory caching (Redis integration optional).
    """
    
    def __init__(self, level: CacheLevel = CacheLevel.MEMORY, max_size: int = 1000):
        """
        Initialize cache service.
        
        Args:
            level: Cache level (MEMORY, REDIS, HYBRID)
            max_size: Max cache entries
        """
        self.level = level
        self.memory_cache = MemoryCache(max_size=max_size)
        
        # Initialize Redis if requested
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_password = os.getenv("REDIS_PASSWORD")
        if redis_password == "":
            redis_password = None
            
        if level in [CacheLevel.REDIS, CacheLevel.HYBRID]:
            self.redis_cache = RedisCache(host=redis_host, port=redis_port, password=redis_password)
        else:
            self.redis_cache = None
            
        logger.info(f"Cache Service initialized (level: {level.value}, max_size: {max_size})")
    
    def _generate_cache_key(self, question: str, intent: Optional[str] = None) -> str:
        """
        Generate cache key from question and intent.
        
        Args:
            question: User question
            intent: Query intent (optional)
            
        Returns:
            Cache key
        """
        key_content = f"{question}:{intent}" if intent else question
        key_hash = hashlib.md5(key_content.encode()).hexdigest() #hash the question and intent to generate a fixed-length key.
        return f"cache:{key_hash[:16]}"
    
    def get_cached_response(
        self,
        question: str,
        intent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached response for question.
        
        Args:
            question: User question
            intent: Query intent (optional)
            
        Returns:
            Cached response or None if not found/expired
            
            
        Its workflow: 
        1. Generate key
        2. Check memory cache
        3. If not found → check Redis
        4. If Redis hit in HYBRID mode:
            populate memory cache
        5. Return result
        """
        key = self._generate_cache_key(question, intent)
        
        if self.level in [CacheLevel.MEMORY, CacheLevel.HYBRID]:
            result = self.memory_cache.get(key)
            if result:
                return result
        
        if self.level in [CacheLevel.REDIS, CacheLevel.HYBRID] and self.redis_cache:
            result = self.redis_cache.get(key)
            if result:
                # If hybrid, populate memory cache from redis
                if self.level == CacheLevel.HYBRID:
                    # Default TTL for hybrid memory cache populating from redis
                    self.memory_cache.set(key, result, ttl_seconds=300)
                return result
        
        return None
    
    def cache_response(
        self,
        question: str,
        response: Dict[str, Any],
        intent: Optional[str] = None,
        ttl_seconds: int = 3600,
        source: str = ""
    ) -> bool:
        """
        Cache query response.
        
        Args:
            question: User question
            response: Response to cache
            intent: Query intent (optional)
            ttl_seconds: Time to live in seconds
            source: Source of response (e.g., "retrieval")
            
        Returns:
            True if successful
        """
        key = self._generate_cache_key(question, intent)
        
        success = True
        
        if self.level in [CacheLevel.MEMORY, CacheLevel.HYBRID]:
            success = self.memory_cache.set(key, response, ttl_seconds, source)
        
        if self.level in [CacheLevel.REDIS, CacheLevel.HYBRID] and self.redis_cache:
            redis_success = self.redis_cache.set(key, response, ttl_seconds, source)
            success = success and redis_success if self.level == CacheLevel.HYBRID else redis_success
        
        return success
    
    def invalidate_cache(self, pattern: Optional[str] = None):
        """
        Invalidate cache entries.
        
        Args:
            pattern: Pattern to match (None = clear all)
        """
        if pattern is None:
            self.memory_cache.clear()
            if self.redis_cache:
                self.redis_cache.clear()
            logger.info("Cache invalidated (all)")
        else:
            # Note: Pattern-based invalidation logic
            logger.info(f"Cache invalidation pattern: {pattern}")
            # Memory cache pattern clearing isn't fully supported without iterating
            if self.redis_cache and self.redis_cache.is_available:
                try:
                    keys = self.redis_cache.client.keys(pattern)
                    if keys:
                        self.redis_cache.client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis invalidation error: {e}")
    
    def cleanup_expired(self):
        """Remove expired cache entries."""
        self.memory_cache.cleanup_expired()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "level": self.level.value,
            "memory": self.memory_cache.get_stats(),
        }
        if self.redis_cache:
            stats["redis"] = self.redis_cache.get_stats()
        return stats


# Global cache service instance
_cache_service: Optional[CacheService] = None


def get_cache_service(
    level: CacheLevel = CacheLevel.MEMORY,
    max_size: int = 1000
) -> CacheService:
    """
    Get or create global cache service.
    
    Args:
        level: Cache level (can be CacheLevel enum or string like "memory")
        max_size: Max cache entries
        
    Returns:
        CacheService instance
    """
    global _cache_service
    
    if _cache_service is None:
        # Convert string to CacheLevel enum if needed
        if isinstance(level, str):
            level = CacheLevel(level)
        
        _cache_service = CacheService(level=level, max_size=max_size)
    
    return _cache_service
