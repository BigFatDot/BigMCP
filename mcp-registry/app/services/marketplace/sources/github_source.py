"""
GitHub Source - Fetch official MCP servers from GitHub.

Extracted from marketplace_service.py for better modularity.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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


class GitHubSource(MarketplaceSource):
    """
    Fetch official MCP servers from GitHub.

    Reads from modelcontextprotocol/servers repository.
    """

    GITHUB_API = "https://api.github.com"
    OFFICIAL_REPO = "modelcontextprotocol/servers"

    def __init__(self, http_client: httpx.AsyncClient):
        super().__init__(http_client)
        self.credential_detector = CredentialDetector()

    async def fetch_servers(self) -> List[MarketplaceServer]:
        """Fetch servers from GitHub repository."""
        servers = []

        try:
            # Get src directory contents
            response = await self.http_client.get(
                f"{self.GITHUB_API}/repos/{self.OFFICIAL_REPO}/contents/src",
                headers={"Accept": "application/vnd.github.v3+json"}
            )

            if response.status_code != 200:
                logger.warning(f"GitHub API failed: {response.status_code}")
                return servers

            contents = response.json()

            for item in contents:
                if item.get("type") == "dir":
                    server = await self._fetch_server_info(item["name"])
                    if server:
                        servers.append(server)

            logger.info(f"Fetched {len(servers)} servers from GitHub")

        except Exception as e:
            logger.error(f"Error fetching from GitHub: {e}")

        return servers

    async def _fetch_server_info(self, server_name: str) -> Optional[MarketplaceServer]:
        """Fetch detailed info for a server directory."""
        try:
            # Try to get package.json
            response = await self.http_client.get(
                f"{self.GITHUB_API}/repos/{self.OFFICIAL_REPO}/contents/src/{server_name}/package.json",
                headers={"Accept": "application/vnd.github.v3+json"}
            )

            if response.status_code == 200:
                content = response.json()
                # Decode base64 content
                package_json = json.loads(base64.b64decode(content["content"]).decode())
                return self._parse_package_json(server_name, package_json)

            # Fallback: create basic entry
            display_name = server_name.replace("-", " ").title()
            package_name = f"@modelcontextprotocol/server-{server_name}"

            # Detect credentials even without package.json
            detected_creds = self.credential_detector.detect_from_name(
                server_name=display_name,
                package_name=package_name
            )
            detected_creds = self.credential_detector.merge_credentials([detected_creds])

            # Convert to CredentialSpec objects
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
                id=f"official-{server_name}",
                name=display_name,
                description=f"Official MCP server: {server_name}",
                install_type=InstallationType.NPM,
                install_package=package_name,
                command="npx",
                args=["-y", package_name],
                source=ServerSource.OFFICIAL,
                source_url=f"https://github.com/{self.OFFICIAL_REPO}/tree/main/src/{server_name}",
                repository=f"https://github.com/{self.OFFICIAL_REPO}",
                author="modelcontextprotocol",
                credentials=credentials,
                verified=True,
                popularity=90,
                discovered_at=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Error fetching GitHub server {server_name}: {e}")
            return None

    def _parse_package_json(
        self, server_name: str, package: Dict[str, Any]
    ) -> MarketplaceServer:
        """Parse package.json into MarketplaceServer."""
        name = package.get("name", f"@modelcontextprotocol/server-{server_name}")
        display_name = server_name.replace("-", " ").title()

        # Detect credentials from server name
        detected_creds = self.credential_detector.detect_from_name(
            server_name=display_name,
            package_name=name
        )

        # Parse credentials from package.json
        package_creds = self.credential_detector.detect_from_package_json(package)
        detected_creds = self.credential_detector.merge_credentials([
            detected_creds,
            package_creds
        ])

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
            id=f"official-{server_name}",
            name=display_name,
            description=package.get("description", ""),
            install_type=InstallationType.NPM,
            install_package=name,
            command="npx",
            args=["-y", name],
            version=package.get("version"),
            source=ServerSource.OFFICIAL,
            source_url=f"https://github.com/{self.OFFICIAL_REPO}/tree/main/src/{server_name}",
            repository=f"https://github.com/{self.OFFICIAL_REPO}",
            author="modelcontextprotocol",
            credentials=credentials,
            tags=package.get("keywords", []),
            verified=True,
            popularity=90,
            discovered_at=datetime.utcnow()
        )
