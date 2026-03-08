"""
BigMCP Source - Load curated servers from BigMCP source file.

Extracted from marketplace_service.py for better modularity.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import httpx

from .base import MarketplaceSource
from ..models import (
    CredentialSpec,
    InstallationType,
    MarketplaceServer,
    ServerSource,
)

if TYPE_CHECKING:
    pass  # No additional type-only imports needed

logger = logging.getLogger(__name__)


class BigMCPSource(MarketplaceSource):
    """
    Load curated servers from BigMCP source file.

    Provides the base curated marketplace data with full tool details.
    Loads from bigmcp_source.json (not to be confused with Local Registry mcp_servers.json).
    """

    def __init__(self, http_client: httpx.AsyncClient, registry_path: Optional[Path] = None):
        super().__init__(http_client)
        # Use bigmcp_source.json as primary source (curated servers with full tool details)
        self.registry_path = registry_path or Path(__file__).parent.parent.parent.parent / "conf" / "bigmcp_source.json"

    async def fetch_servers(self) -> List[MarketplaceServer]:
        """Load servers from BigMCP source file."""
        servers = []

        try:
            if not self.registry_path.exists():
                logger.warning(f"BigMCP source not found: {self.registry_path}")
                return servers

            with open(self.registry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for server_id, server_data in data.get("servers", {}).items():
                server = self._parse_bigmcp_entry(server_id, server_data)
                if server:
                    servers.append(server)

            logger.info(f"Loaded {len(servers)} servers from BigMCP source")

        except Exception as e:
            logger.error(f"Error loading BigMCP source: {e}")

        return servers

    def _parse_bigmcp_entry(
        self, server_id: str, data: Dict[str, Any]
    ) -> Optional[MarketplaceServer]:
        """Parse BigMCP source entry from bigmcp_source.json."""
        try:
            install_info = data.get("install", {})

            # Parse credentials with full documentation support
            credentials = []
            for cred_data in data.get("credentials", []):
                credentials.append(CredentialSpec(
                    name=cred_data.get("name", ""),
                    description=cred_data.get("description", ""),
                    required=cred_data.get("required", True),
                    type=cred_data.get("type", "secret"),
                    config_type=cred_data.get("configType", "remote"),
                    default=cred_data.get("default"),
                    example=cred_data.get("example"),
                    documentation_url=cred_data.get("documentationUrl")
                ))

            # Parse tools with full details (name, description, isReadOnly, isDestructive)
            tools = []
            for tool_data in data.get("tools", []):
                tools.append({
                    "name": tool_data.get("name", ""),
                    "description": tool_data.get("description", ""),
                    "is_read_only": tool_data.get("isReadOnly", False),
                    "is_destructive": tool_data.get("isDestructive", False)
                })

            # Determine source based on "official" flag
            source = ServerSource.OFFICIAL if data.get("official", False) else ServerSource.BIGMCP

            return MarketplaceServer(
                id=server_id,
                name=data.get("name", server_id),
                description=data.get("description", data.get("shortDescription", "")),
                install_type=InstallationType(install_info.get("type", "npm")),
                install_package=install_info.get("package", install_info.get("image", "")),
                command=data.get("command"),
                args=data.get("args", []),
                env=data.get("env", {}),
                source=source,
                source_url=data.get("repository"),
                repository=data.get("repository"),
                author=data.get("author"),
                icon_url=data.get("iconUrl"),
                credentials=credentials,
                category=data.get("category"),
                tags=data.get("tags", []),
                verified=data.get("verified", False),
                popularity=data.get("popularity", 50),
                tools=tools,
                tools_preview=data.get("toolsPreview", []),
                requires_local_access=data.get("requiresLocalAccess", False),
                discovered_at=datetime.utcnow(),
                is_curated=True,
                service_id=data.get("service_id")
            )

        except Exception as e:
            logger.error(f"Error parsing local entry {server_id}: {e}")
            return None
