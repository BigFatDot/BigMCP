"""
Marketplace Source Base Class - Abstract base for data sources.

Extracted from marketplace_service.py for better modularity.

NOTE: Uses TYPE_CHECKING to avoid circular imports at runtime.
Type annotations use string form ("MarketplaceServer") for forward references.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

import httpx

if TYPE_CHECKING:
    from ..models import MarketplaceServer


class MarketplaceSource(ABC):
    """Base class for marketplace data sources."""

    def __init__(self, http_client: httpx.AsyncClient):
        self.http_client = http_client

    @abstractmethod
    async def fetch_servers(self) -> List["MarketplaceServer"]:
        """Fetch servers from this source."""
        raise NotImplementedError

    async def fetch_server_details(self, server_id: str) -> Optional["MarketplaceServer"]:
        """Fetch detailed info for a specific server."""
        raise NotImplementedError
