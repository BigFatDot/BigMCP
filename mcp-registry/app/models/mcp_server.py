"""
MCP Server model for multi-tenant server management.

Each organization can add, configure, and manage their own MCP servers.
Replaces the global mcp_servers.json configuration with database-driven approach.
"""

import enum
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class InstallType(str, enum.Enum):
    """Installation method for MCP server."""
    PIP = "pip"  # Python package (pip install)
    NPM = "npm"  # Node.js package (npm install)
    GITHUB = "github"  # Clone from GitHub
    DOCKER = "docker"  # Docker container
    LOCAL = "local"  # Already installed locally


class ServerStatus(str, enum.Enum):
    """Runtime status of MCP server."""
    STOPPED = "stopped"  # Not running
    STARTING = "starting"  # Initialization in progress
    RUNNING = "running"  # Active and ready
    ERROR = "error"  # Failed to start or crashed
    DISABLED = "disabled"  # Manually disabled by user


class MCPServer(Base, UUIDMixin, TimestampMixin):
    """
    MCP Server configuration for multi-tenant server management.

    Each server:
    - Belongs to an organization (multi-tenant isolation)
    - Has installation configuration (pip, npm, github, docker)
    - Has runtime configuration (command, args, env vars)
    - Exposes tools to the organization
    - Can be started/stopped/reconfigured dynamically

    This replaces the global mcp_servers.json with database-driven config.
    """

    __tablename__ = "mcp_servers"

    # Organization ownership (multi-tenant isolation)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Server identification
    server_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Unique identifier for server within organization (e.g., 'grist-mcp')"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="User-friendly alias for this instance (e.g., 'personal', 'work')"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Installation configuration
    install_type: Mapped[InstallType] = mapped_column(
        String(50),
        nullable=False,
        comment="How to install this server"
    )
    install_package: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Package name or repository URL"
    )
    version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Specific version to install (null = latest)"
    )

    # Runtime configuration
    command: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Command to execute (e.g., 'python', 'node')"
    )
    args: Mapped[list] = mapped_column(
        JSONType,
        default=[],
        nullable=False,
        comment="Command arguments as JSON array"
    )
    env: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Environment variables as JSON object"
    )

    # Status & Health
    status: Mapped[ServerStatus] = mapped_column(
        String(50),
        default=ServerStatus.STOPPED,
        nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_visible_to_oauth_clients: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="If False, server is hidden from OAuth clients but available for API keys"
    )
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Statistics
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="mcp_servers"
    )

    tools: Mapped[List["Tool"]] = relationship(
        "Tool",
        back_populates="server",
        cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("organization_id", "server_id", name="uq_org_server"),
    )

    def __repr__(self) -> str:
        return f"<MCPServer(id={self.id}, server_id={self.server_id}, org={self.organization_id}, status={self.status})>"

    def to_dict(self) -> dict:
        """
        Convert to dictionary format compatible with legacy mcp_servers.json.

        This allows backward compatibility with existing code that expects
        the old configuration format.
        """
        return {
            "id": str(self.id),
            "server_id": self.server_id,
            "name": self.name,
            "alias": self.alias,
            "description": self.description,
            "install": {
                "type": self.install_type,
                "package": self.install_package,
                "version": self.version
            },
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "status": self.status,
            "enabled": self.enabled,
            "last_connected_at": self.last_connected_at.isoformat() if self.last_connected_at else None,
            "error_message": self.error_message,
            "statistics": {
                "total_requests": self.total_requests,
                "failed_requests": self.failed_requests
            }
        }

    @classmethod
    def from_json_config(
        cls,
        organization_id: UUID,
        server_id: str,
        config: dict
    ) -> "MCPServer":
        """
        Create MCPServer from legacy mcp_servers.json format.

        Useful for migrating existing configurations to database.

        Args:
            organization_id: Organization to own this server
            server_id: Server identifier
            config: Configuration dict from mcp_servers.json

        Returns:
            MCPServer instance ready to be added to session
        """
        install_config = config.get("install", {})

        return cls(
            organization_id=organization_id,
            server_id=server_id,
            name=config.get("name", server_id),
            description=config.get("description"),
            install_type=install_config.get("type", "pip"),
            install_package=install_config.get("package", ""),
            version=install_config.get("version"),
            command=config.get("command", "python"),
            args=config.get("args", []),
            env=config.get("env", {}),
            enabled=config.get("enabled", True)
        )
