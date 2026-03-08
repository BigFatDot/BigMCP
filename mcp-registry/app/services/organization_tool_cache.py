"""
Organization Tool Cache - Performance cache for tool discovery.

Provides < 5ms tool listing by caching tools per organization.
Fully multi-tenant with automatic cache invalidation.

Note: This cache stores ORM Tool objects and keeps in-memory storage
regardless of CacheBackend (Redis/memory). ORM objects aren't
JSON-serializable, and the 5-min TTL makes Redis migration low-value
for single-instance deployments. For multi-instance (Phase 3),
invalidation signals are propagated via CacheBackend.
"""

import logging
from typing import List, Optional, Dict
from uuid import UUID
from datetime import datetime, timedelta
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .tool_service import ToolService

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached tools for an organization."""
    oauth_tools: List  # Tools visible to OAuth clients
    api_tools: List  # All tools available via API keys
    cached_at: datetime
    ttl_seconds: int = 300  # 5 minutes

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.utcnow() > (self.cached_at + timedelta(seconds=self.ttl_seconds))


class OrganizationToolCache:
    """
    In-memory cache for organization tools.

    Multi-tenant design:
    - Each organization has its own cache entry
    - Cache key = organization_id
    - Automatic isolation between organizations
    - TTL-based expiration (5 minutes)

    Performance target: < 5ms for cache hit

    Usage:
        cache = OrganizationToolCache()
        tools = await cache.get_tools_for_oauth(db, organization_id)
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 300s = 5min)
        """
        self._cache: Dict[UUID, CacheEntry] = {}
        self.ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    async def get_tools_for_oauth(
        self,
        db: AsyncSession,
        organization_id: UUID,
        server_id: Optional[str] = None
    ) -> List:
        """
        Get tools visible to OAuth clients.

        Performance: < 5ms for cache hit, ~50ms for cache miss

        Args:
            db: Database session
            organization_id: Organization UUID
            server_id: Optional server filter

        Returns:
            List of Tool objects visible to OAuth clients
        """
        # Check cache
        entry = self._cache.get(organization_id)

        if entry and not entry.is_expired() and not server_id:
            # Cache hit (no server filter)
            self._hits += 1
            logger.debug(
                f"Cache HIT for org {organization_id} (OAuth): "
                f"{len(entry.oauth_tools)} tools"
            )
            return entry.oauth_tools

        # Cache miss or expired - fetch from DB
        self._misses += 1
        logger.debug(f"Cache MISS for org {organization_id} (OAuth)")

        service = ToolService(db)
        tools = await service.list_tools_for_oauth(organization_id, server_id)

        # Update cache (only if no server filter)
        if not server_id:
            if entry:
                # Update existing entry's OAuth tools
                entry.oauth_tools = tools
                entry.cached_at = datetime.utcnow()
            else:
                # Create new entry
                self._cache[organization_id] = CacheEntry(
                    oauth_tools=tools,
                    api_tools=[],  # Will be populated on first API key request
                    cached_at=datetime.utcnow(),
                    ttl_seconds=self.ttl_seconds
                )

        return tools

    async def get_tools_for_api_key(
        self,
        db: AsyncSession,
        organization_id: UUID,
        tool_group_id: Optional[UUID] = None,
        server_id: Optional[str] = None
    ) -> List:
        """
        Get tools accessible via API key.

        Performance: < 5ms for cache hit (without filters), ~50ms for cache miss

        Args:
            db: Database session
            organization_id: Organization UUID
            tool_group_id: Optional tool group filter
            server_id: Optional server filter

        Returns:
            List of Tool objects accessible via API keys
        """
        # Check cache (only if no filters)
        if not tool_group_id and not server_id:
            entry = self._cache.get(organization_id)

            if entry and not entry.is_expired():
                # Cache hit
                self._hits += 1
                logger.debug(
                    f"Cache HIT for org {organization_id} (API): "
                    f"{len(entry.api_tools)} tools"
                )
                return entry.api_tools

        # Cache miss or filtered request - fetch from DB
        self._misses += 1
        logger.debug(
            f"Cache MISS for org {organization_id} (API) "
            f"[group={tool_group_id}, server={server_id}]"
        )

        service = ToolService(db)
        tools = await service.list_tools_for_api_key(
            organization_id,
            tool_group_id,
            server_id
        )

        # Update cache (only if no filters)
        if not tool_group_id and not server_id:
            entry = self._cache.get(organization_id)
            if entry:
                # Update existing entry's API tools
                entry.api_tools = tools
                entry.cached_at = datetime.utcnow()
            else:
                # Create new entry
                self._cache[organization_id] = CacheEntry(
                    oauth_tools=[],  # Will be populated on first OAuth request
                    api_tools=tools,
                    cached_at=datetime.utcnow(),
                    ttl_seconds=self.ttl_seconds
                )

        return tools

    async def invalidate_organization(self, organization_id: UUID) -> None:
        """
        Invalidate cache for a specific organization.

        Call this when:
        - Server visibility changes
        - Tool visibility changes
        - Server is added/removed
        - Tools are discovered

        Also signals via CacheBackend for cross-instance invalidation.

        Args:
            organization_id: Organization UUID to invalidate
        """
        if organization_id in self._cache:
            del self._cache[organization_id]
            logger.info(f"Cache invalidated for organization {organization_id}")

        # Signal invalidation via CacheBackend (for multi-instance)
        try:
            from ..core.cache_backend import get_cache_backend
            backend = get_cache_backend()
            await backend.delete(f"org_cache_valid:{organization_id}")
        except Exception:
            pass  # Best-effort signaling

    async def invalidate_all(self) -> None:
        """Invalidate entire cache."""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache fully invalidated ({count} organizations)")

        # Signal invalidation via CacheBackend
        try:
            from ..core.cache_backend import get_cache_backend
            backend = get_cache_backend()
            await backend.delete_pattern("org_cache_valid:*")
        except Exception:
            pass

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats (hits, misses, hit_rate, size)
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
            "cache_size": len(self._cache),
            "ttl_seconds": self.ttl_seconds,
        }

    def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        expired = [
            org_id for org_id, entry in self._cache.items()
            if entry.is_expired()
        ]

        for org_id in expired:
            del self._cache[org_id]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired cache entries")

        return len(expired)


# Global singleton instance
tool_cache = OrganizationToolCache(ttl_seconds=300)
