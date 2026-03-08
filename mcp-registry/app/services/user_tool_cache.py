"""
User Tool State Cache Service.

Provides instant tool listing for OAuth clients by caching the last known
tool state per user. This avoids the 35-70 second server startup delay
on first OAuth client connection.

Cache lifecycle:
- Populated after successful tool discovery from user servers
- Returned instantly on OAuth tool list requests
- Triggers async server startup in background for fresh data
- Invalidated on logout or manual user server changes

Backend:
- Uses CacheBackend abstraction (Redis or in-memory fallback)
- Redis keys: user_tools:{user_id}, user_tools_org:{org_id}
"""

import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CachedToolState:
    """Cached tool state for a user."""
    user_id: UUID
    organization_id: UUID
    tools: List[Dict]  # List of tool dictionaries (serializable)
    server_ids: Set[str]  # Server IDs that were active
    cached_at: datetime
    expires_at: datetime


class UserToolCache:
    """
    Cache of last known tool states per user.

    Uses CacheBackend for storage (Redis or in-memory).
    OAuth clients get instant responses (< 5ms) while servers
    start up in the background.
    """

    def __init__(self, cache_ttl_seconds: int = 3600):
        """
        Initialize user tool cache.

        Args:
            cache_ttl_seconds: How long to keep cached tool states (default: 1 hour)
        """
        self.cache_ttl = cache_ttl_seconds
        logger.info(f"UserToolCache initialized with TTL={cache_ttl_seconds}s")

    def _backend(self):
        """Get the cache backend lazily to avoid import-time issues."""
        from ..core.cache_backend import get_cache_backend
        return get_cache_backend()

    def _key(self, user_id: UUID) -> str:
        return f"user_tools:{user_id}"

    def _org_key(self, organization_id: UUID) -> str:
        return f"user_tools_org:{organization_id}"

    async def get(self, user_id: UUID) -> Optional[List[Dict]]:
        """
        Get cached tools for a user.

        Returns:
            List of tool dictionaries if cache hit, None if cache miss
        """
        backend = self._backend()
        data = await backend.get(self._key(user_id))

        if data is None:
            logger.info(f"Cache MISS for user {user_id}")
            return None

        tools = data.get("tools", [])
        server_count = len(data.get("server_ids", []))
        cached_at = data.get("cached_at", "")

        logger.info(
            f"Cache HIT for user {user_id}: {len(tools)} tools "
            f"from {server_count} servers (cached_at: {cached_at})"
        )
        return tools

    async def set(
        self,
        user_id: UUID,
        organization_id: UUID,
        tools: List[Dict],
        server_ids: Set[str]
    ) -> None:
        """
        Update cached tool state for a user.

        Args:
            user_id: User UUID
            organization_id: Organization UUID
            tools: List of tool dictionaries (must be JSON-serializable)
            server_ids: Set of server IDs that provided these tools
        """
        backend = self._backend()
        now = datetime.utcnow()

        data = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "tools": tools,
            "server_ids": list(server_ids),
            "cached_at": now.isoformat(),
        }

        await backend.set(self._key(user_id), data, ttl=self.cache_ttl)

        # Maintain org→users index for org-wide invalidation.
        # Always re-set with full TTL to prevent the index from expiring
        # while user caches are still active (which would break invalidate_organization).
        org_key = self._org_key(organization_id)
        org_data = await backend.get(org_key) or []
        user_id_str = str(user_id)
        if user_id_str not in org_data:
            org_data.append(user_id_str)
        # Always reset TTL on org index (even if user was already present)
        await backend.set(org_key, org_data, ttl=self.cache_ttl)

        logger.info(
            f"Cached {len(tools)} tools from {len(server_ids)} servers "
            f"for user {user_id}"
        )

    async def invalidate(self, user_id: UUID) -> bool:
        """
        Invalidate cache for a specific user.

        Returns:
            True if cache was invalidated, False if no cache existed
        """
        backend = self._backend()
        key = self._key(user_id)

        existed = await backend.exists(key)
        if existed:
            await backend.delete(key)
            logger.info(f"Invalidated cache for user {user_id}")
            return True

        return False

    async def invalidate_organization(self, organization_id: UUID) -> int:
        """
        Invalidate cache for all users in an organization.

        Useful when organization-wide changes occur (e.g., team server added).

        Returns:
            Number of cache entries invalidated
        """
        backend = self._backend()
        org_key = self._org_key(organization_id)

        user_ids = await backend.get(org_key) or []
        count = 0
        for uid_str in user_ids:
            key = f"user_tools:{uid_str}"
            if await backend.exists(key):
                await backend.delete(key)
                count += 1

        if count > 0:
            await backend.delete(org_key)
            logger.info(
                f"Invalidated cache for {count} users "
                f"in organization {organization_id}"
            )

        return count

    async def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        For Redis backend, TTL handles this natively (returns 0).
        For in-memory backend, delegates to backend.cleanup_expired().

        Returns:
            Number of entries removed
        """
        backend = self._backend()
        removed = await backend.cleanup_expired()
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache entries")
        return removed

    def get_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        # Note: This is sync because callers expect sync.
        # For basic stats we return what we can synchronously.
        return {
            "cache_ttl_seconds": self.cache_ttl,
            "backend": "check /api/v1/admin/pool-stats for details",
        }


# Global singleton instance
_user_tool_cache: Optional[UserToolCache] = None


def get_user_tool_cache() -> UserToolCache:
    """Get the global user tool cache instance."""
    global _user_tool_cache

    if _user_tool_cache is None:
        _user_tool_cache = UserToolCache(cache_ttl_seconds=3600)  # 1 hour

    return _user_tool_cache
