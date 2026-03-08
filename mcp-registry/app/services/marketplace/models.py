"""
Marketplace Models - Data structures for MCP server marketplace.

Contains enums and dataclasses used across the marketplace module.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class InstallationType(str, Enum):
    """Installation method for MCP servers."""
    NPM = "npm"
    PIP = "pip"
    GITHUB = "github"
    DOCKER = "docker"
    LOCAL = "local"
    REMOTE = "remote"  # SSE-based remote server


class ServerSource(str, Enum):
    """Source registry for the server."""
    CUSTOM = "custom"  # User-added (priority 1)
    BIGMCP = "bigmcp"  # BigMCP curated list (priority 2)
    OFFICIAL = "official"  # modelcontextprotocol org (priority 3)
    NPM = "npm"  # npm registry (priority 4, LLM curated)
    GITHUB = "github"  # GitHub repos (priority 5, LLM curated)
    GLAMA = "glama"  # Glama.ai registry (disabled)
    SMITHERY = "smithery"  # Smithery.ai marketplace (disabled)


@dataclass
class CredentialSpec:
    """Specification for a required credential."""
    name: str
    description: str
    required: bool = True
    type: str = "secret"  # secret, string, url, path, oauth
    config_type: str = "remote"  # remote (API keys), local (localhost configs)
    default: Optional[str] = None
    example: Optional[str] = None
    documentation_url: Optional[str] = None


@dataclass
class MarketplaceServer:
    """
    Normalized MCP server entry from marketplace.

    Combines data from multiple sources into a unified format.
    """
    id: str
    name: str
    description: str

    # Installation
    install_type: InstallationType
    install_package: str  # npm package, pip package, github repo, docker image
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)

    # Source & metadata
    source: ServerSource = ServerSource.BIGMCP
    source_url: Optional[str] = None
    repository: Optional[str] = None
    author: Optional[str] = None
    version: Optional[str] = None
    icon_url: Optional[str] = None

    # Credentials
    credentials: List[CredentialSpec] = field(default_factory=list)

    # Categorization
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Quality indicators
    verified: bool = False
    popularity: int = 0  # 0-100 score
    downloads_weekly: Optional[int] = None

    # Tools - full details from static analysis
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tools_preview: List[str] = field(default_factory=list)

    # SaaS compatibility (from static analysis)
    requires_local_access: bool = False

    # Curation flag
    is_curated: bool = False

    # Service identification for deduplication
    service_id: Optional[str] = None

    # Availability (from static analysis)
    is_available: bool = True
    availability_reason: Optional[str] = None

    # Dynamic tools flag
    has_dynamic_tools: bool = False

    # Timestamps
    last_updated: Optional[datetime] = None
    discovered_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['install_type'] = self.install_type.value
        data['source'] = self.source.value
        # Convert credentials
        data['credentials'] = [asdict(c) for c in self.credentials]

        # Analyze credentials: separate required vs optional
        required_creds = [c for c in self.credentials if c.required]
        optional_creds = [c for c in self.credentials if not c.required]

        # Analyze credentials: separate local vs remote
        local_creds = [c for c in self.credentials if c.config_type == "local"]
        remote_creds = [c for c in self.credentials if c.config_type != "local"]

        # Set credential flags for frontend
        data['requires_credentials'] = len(required_creds) > 0
        data['has_optional_credentials'] = len(optional_creds) > 0
        data['required_credentials_count'] = len(required_creds)
        data['optional_credentials_count'] = len(optional_creds)

        # Local vs remote credential flags
        data['has_local_credentials'] = len(local_creds) > 0
        data['has_remote_credentials'] = len(remote_creds) > 0

        # Add is_official and is_verified flags for frontend
        data['is_official'] = self.source == ServerSource.OFFICIAL
        data['is_verified'] = self.verified
        data['tools_count'] = len(self.tools) if self.tools else len(self.tools_preview)

        # Convert datetimes
        if self.last_updated:
            data['last_updated'] = self.last_updated.isoformat()
        if self.discovered_at:
            data['discovered_at'] = self.discovered_at.isoformat()
        return data
