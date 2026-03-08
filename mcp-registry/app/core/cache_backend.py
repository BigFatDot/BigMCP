"""
Cache backend abstraction.

Provides a unified interface for caching with two implementations:
- InMemoryCacheBackend: dict-based, used as fallback
- RedisCacheBackend: Redis-based, for production scaling

Usage:
    backend = get_cache_backend()
    await backend.set("key", {"data": "value"}, ttl=300)
    data = await backend.get("key")
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key. Returns None if not found or expired."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value with optional TTL in seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a single key."""

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (e.g. 'prefix:*'). Returns count deleted."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter. Creates with value=amount if not exists."""

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> None:
        """Set TTL on existing key."""

    @abstractmethod
    async def get_stats(self) -> dict:
        """Get cache statistics."""

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed. No-op for Redis."""


class InMemoryCacheBackend(CacheBackend):
    """
    In-memory cache backend using dict.

    Used as fallback when Redis is unavailable.
    Stores values with expiry timestamps.
    """

    def __init__(self):
        # {key: (value, expire_at)} where expire_at is None for no-expiry
        self._store: dict[str, tuple[Any, Optional[float]]] = {}
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        value, expire_at = entry
        if expire_at is not None and time.time() > expire_at:
            del self._store[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expire_at = (time.time() + ttl) if ttl else None
        self._store[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        # Simple glob matching: only supports trailing *
        prefix = pattern.rstrip("*")
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)

    async def exists(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        _, expire_at = entry
        if expire_at is not None and time.time() > expire_at:
            del self._store[key]
            return False
        return True

    async def incr(self, key: str, amount: int = 1) -> int:
        entry = self._store.get(key)
        if entry is None:
            self._store[key] = (amount, None)
            return amount

        value, expire_at = entry
        if expire_at is not None and time.time() > expire_at:
            self._store[key] = (amount, None)
            return amount

        new_value = int(value) + amount
        self._store[key] = (new_value, expire_at)
        return new_value

    async def expire(self, key: str, ttl: int) -> None:
        entry = self._store.get(key)
        if entry is not None:
            value, _ = entry
            self._store[key] = (value, time.time() + ttl)

    async def get_stats(self) -> dict:
        now = time.time()
        active = sum(
            1 for _, (_, exp) in self._store.items()
            if exp is None or exp > now
        )
        return {
            "backend": "memory",
            "total_keys": len(self._store),
            "active_keys": active,
            "hits": self._hits,
            "misses": self._misses,
        }

    async def cleanup_expired(self) -> int:
        now = time.time()
        expired = [
            k for k, (_, exp) in self._store.items()
            if exp is not None and exp < now
        ]
        for k in expired:
            del self._store[k]
        return len(expired)


class RedisCacheBackend(CacheBackend):
    """
    Redis cache backend.

    Uses JSON serialization for complex values.
    Relies on Redis native TTL for expiry.
    """

    def __init__(self, redis_client, prefix: str = "bigmcp:"):
        self._redis = redis_client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        """Prefix key if not already prefixed."""
        if key.startswith(self._prefix):
            return key
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        try:
            raw = await self._redis.get(self._key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
        except Exception as e:
            logger.warning(f"Redis GET error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                await self._redis.setex(self._key(key), ttl, serialized)
            else:
                await self._redis.set(self._key(key), serialized)
        except Exception as e:
            logger.warning(f"Redis SET error for {key}: {e}")

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(self._key(key))
        except Exception as e:
            logger.warning(f"Redis DELETE error for {key}: {e}")

    async def delete_pattern(self, pattern: str) -> int:
        try:
            full_pattern = self._key(pattern)
            count = 0
            async for key in self._redis.scan_iter(match=full_pattern, count=100):
                await self._redis.delete(key)
                count += 1
            return count
        except Exception as e:
            logger.warning(f"Redis DELETE_PATTERN error for {pattern}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(self._key(key)))
        except Exception as e:
            logger.warning(f"Redis EXISTS error for {key}: {e}")
            return False

    async def incr(self, key: str, amount: int = 1) -> int:
        try:
            return await self._redis.incrby(self._key(key), amount)
        except Exception as e:
            logger.warning(f"Redis INCR error for {key}: {e}")
            return 0

    async def expire(self, key: str, ttl: int) -> None:
        try:
            await self._redis.expire(self._key(key), ttl)
        except Exception as e:
            logger.warning(f"Redis EXPIRE error for {key}: {e}")

    async def get_stats(self) -> dict:
        try:
            info = await self._redis.info("keyspace")
            db_info = info.get("db0", {})
            return {
                "backend": "redis",
                "total_keys": db_info.get("keys", 0) if isinstance(db_info, dict) else 0,
                "connected": True,
            }
        except Exception as e:
            return {
                "backend": "redis",
                "connected": False,
                "error": str(e),
            }

    async def cleanup_expired(self) -> int:
        # Redis handles TTL natively, no-op
        return 0


# =============================================================================
# Singleton & Factory
# =============================================================================

_cache_backend: Optional[CacheBackend] = None


def get_cache_backend() -> CacheBackend:
    """
    Get the active cache backend.

    Returns RedisCacheBackend if Redis is connected,
    otherwise InMemoryCacheBackend.
    """
    global _cache_backend
    if _cache_backend is None:
        _cache_backend = InMemoryCacheBackend()
        logger.info("Cache backend initialized: in-memory")
    return _cache_backend


def init_cache_backend(redis_client=None, prefix: str = "bigmcp:") -> CacheBackend:
    """
    Initialize cache backend with optional Redis client.

    Call this during app startup after Redis connection is established.
    """
    global _cache_backend
    if redis_client is not None:
        _cache_backend = RedisCacheBackend(redis_client, prefix)
        logger.info("Cache backend initialized: redis")
    else:
        _cache_backend = InMemoryCacheBackend()
        logger.info("Cache backend initialized: in-memory (fallback)")
    return _cache_backend
