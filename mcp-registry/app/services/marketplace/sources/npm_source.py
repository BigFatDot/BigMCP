"""
NPM Source - Fetch MCP servers from npm registry.

Extracted from marketplace_service.py for better modularity.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import httpx

from .base import MarketplaceSource
from ..models import (
    CredentialSpec,
    InstallationType,
    MarketplaceServer,
    ServerSource,
)
from ...credential_detector import CredentialDetector

if TYPE_CHECKING:
    pass  # No additional type-only imports needed

logger = logging.getLogger(__name__)


class NPMSource(MarketplaceSource):
    """
    Fetch MCP servers from npm registry.

    Searches for:
    - @modelcontextprotocol/* packages
    - Packages with 'mcp-server' in name
    """

    NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
    NPM_PACKAGE_URL = "https://registry.npmjs.org"

    def __init__(self, http_client: httpx.AsyncClient):
        super().__init__(http_client)
        self.credential_detector = CredentialDetector()

    async def fetch_servers(self) -> List[MarketplaceServer]:
        """Fetch MCP servers from npm."""
        servers = []

        # Search queries
        queries = [
            "@modelcontextprotocol/server",
            "mcp-server",
            "modelcontextprotocol"
        ]

        seen_packages: Set[str] = set()

        for query in queries:
            try:
                response = await self.http_client.get(
                    self.NPM_SEARCH_URL,
                    params={"text": query, "size": 100}
                )

                if response.status_code != 200:
                    logger.warning(f"npm search failed for '{query}': {response.status_code}")
                    continue

                data = response.json()

                for result in data.get("objects", []):
                    package = result.get("package", {})
                    name = package.get("name", "")

                    # Skip if already seen
                    if name in seen_packages:
                        continue
                    seen_packages.add(name)

                    # Filter for actual MCP servers
                    if not self._is_mcp_server(package):
                        continue

                    server = self._parse_npm_package(package, result)
                    if server:
                        servers.append(server)

            except Exception as e:
                logger.error(f"Error fetching from npm for '{query}': {e}")

        logger.info(f"Fetched {len(servers)} servers from npm")
        return servers

    def _is_mcp_server(self, package: Dict[str, Any]) -> bool:
        """Check if package is an MCP server."""
        name = package.get("name", "").lower()
        description = package.get("description", "").lower()
        keywords = [k.lower() for k in package.get("keywords", [])]

        # Official packages
        if name.startswith("@modelcontextprotocol/server"):
            return True

        # Name patterns
        if "mcp-server" in name or "mcp_server" in name:
            return True

        # Keywords
        if "mcp" in keywords and "server" in keywords:
            return True

        # Description patterns
        if "model context protocol" in description and "server" in description:
            return True

        return False

    def _parse_npm_package(
        self, package: Dict[str, Any], result: Dict[str, Any]
    ) -> Optional[MarketplaceServer]:
        """Parse npm package into MarketplaceServer."""
        try:
            name = package.get("name", "")

            # Generate server ID
            server_id = name.replace("@", "").replace("/", "-")

            # Determine if official
            is_official = name.startswith("@modelcontextprotocol/")

            # Clean display name
            display_name = self._clean_name(name)

            # Detect credentials from name and README
            detected_creds = self.credential_detector.detect_from_name(
                server_name=display_name,
                package_name=name
            )

            # Parse credentials from README if available
            readme = package.get("readme", "")
            if readme:
                readme_creds = self.credential_detector.detect_from_readme(readme)
                detected_creds = self.credential_detector.merge_credentials([
                    detected_creds,
                    readme_creds
                ])
            else:
                # Convert to dict format
                detected_creds = self.credential_detector.merge_credentials([detected_creds])

            # Convert detected credentials to CredentialSpec objects
            credentials = [
                CredentialSpec(
                    name=cred["name"],
                    description=cred.get("description", ""),
                    required=cred.get("required", True),
                    type=cred.get("type", "secret"),
                    config_type=cred.get("configType", "remote"),
                    default=cred.get("default"),
                    example=cred.get("example"),
                    documentation_url=cred.get("documentationUrl")
                )
                for cred in detected_creds
            ]

            return MarketplaceServer(
                id=server_id,
                name=display_name,
                description=package.get("description", ""),
                install_type=InstallationType.NPM,
                install_package=name,
                command="npx",
                args=["-y", name],
                source=ServerSource.OFFICIAL if is_official else ServerSource.NPM,
                source_url=f"https://www.npmjs.com/package/{name}",
                repository=package.get("links", {}).get("repository"),
                author=package.get("author", {}).get("name") if isinstance(package.get("author"), dict) else package.get("author"),
                version=package.get("version"),
                credentials=credentials,
                category=self._detect_category(package),
                tags=package.get("keywords", []),
                verified=is_official,
                popularity=self._calculate_popularity(result),
                downloads_weekly=result.get("score", {}).get("detail", {}).get("popularity"),
                discovered_at=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"Error parsing npm package {package.get('name')}: {e}")
            return None

    def _clean_name(self, name: str) -> str:
        """Clean package name for display."""
        original = name
        scope = None

        # Extract scope if present (@scope/package)
        if "/" in name:
            parts = name.split("/")
            scope = parts[0].replace("@", "")
            name = parts[-1]

        # Remove common prefixes/suffixes
        for prefix in ["server-", "mcp-server-", "mcp_server_", "mcp-"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
        for suffix in ["-mcp-server", "-mcp", "-server"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]

        # If name is now empty or just generic, use the scope name
        if not name or name in ["mcp-server", "server", "mcp", ""]:
            if scope and scope not in ["modelcontextprotocol"]:
                name = scope
            else:
                name = original.replace("@", "").replace("/", "-")

        return name.replace("-", " ").replace("_", " ").title()

    def _detect_category(self, package: Dict[str, Any]) -> Optional[str]:
        """Detect category from package metadata."""
        keywords = [k.lower() for k in package.get("keywords", [])]
        description = package.get("description", "").lower()

        category_patterns = {
            "data": ["database", "sql", "postgres", "mysql", "sqlite", "data"],
            "documents": ["file", "filesystem", "document", "pdf"],
            "communication": ["slack", "email", "chat", "messaging"],
            "development": ["git", "github", "code", "browser", "puppeteer"],
            "search": ["search", "web", "fetch", "scraping"],
            "productivity": ["notion", "todoist", "calendar", "task"],
            "cloud": ["aws", "azure", "gcp", "cloud", "s3"],
            "ai": ["memory", "knowledge", "llm", "ai"]
        }

        for category, patterns in category_patterns.items():
            for pattern in patterns:
                if pattern in keywords or pattern in description:
                    return category

        return None

    def _calculate_popularity(self, result: Dict[str, Any]) -> int:
        """Calculate 0-100 popularity score."""
        score = result.get("score", {})
        final_score = score.get("final", 0)
        return int(final_score * 100)
