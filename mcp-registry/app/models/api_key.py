"""
API Key model for authentication.

Provides long-lived tokens for programmatic access (Claude Desktop, scripts, integrations).
"""

import enum
import secrets
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import String, Text, ForeignKey, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import ArrayType


class APIKeyScope(str, enum.Enum):
    """Scopes defining permissions for API keys."""
    TOOLS_READ = "tools:read"  # Read tools and tool metadata
    TOOLS_EXECUTE = "tools:execute"  # Execute tools
    CREDENTIALS_READ = "credentials:read"  # Read user credentials
    CREDENTIALS_WRITE = "credentials:write"  # Create/update user credentials
    SERVERS_READ = "servers:read"  # Read MCP server configurations
    SERVERS_WRITE = "servers:write"  # Create/update MCP server configurations
    ADMIN = "admin"  # Full administrative access


class APIKey(Base, UUIDMixin, TimestampMixin):
    """
    API Key for programmatic authentication.

    API Keys provide long-lived authentication tokens for:
    - Claude Desktop MCP connections
    - Scripts and automation
    - Third-party integrations (Zapier, Make, n8n)
    - CI/CD pipelines

    Security features:
    - Hashed with bcrypt (like passwords)
    - Key prefix shown for identification (mcphub_sk_abc...)
    - Scopes for granular permissions
    - Optional Tool Group restriction
    - Expiration and activity tracking
    """

    __tablename__ = "api_keys"

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this API key"
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization (for multi-tenancy)"
    )

    # API Key data
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name (e.g., 'Claude Desktop - Work Laptop')"
    )

    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt hash of the API key secret"
    )

    key_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="First 8 chars of key for display (e.g., 'mcphub_sk_abc12345')"
    )

    # Permissions
    scopes: Mapped[list[str]] = mapped_column(
        ArrayType,
        nullable=False,
        default=list,
        comment="List of scopes (permissions) granted to this key"
    )

    # Optional Tool Group restriction
    tool_group_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tool_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="If set, this key only has access to tools in this Tool Group"
    )

    # Status and lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this key can be used for authentication"
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiration date (null = never expires)"
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this key was used for authentication"
    )

    last_used_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address from last use (IPv4 or IPv6)"
    )

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of what this key is used for"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    organization: Mapped["Organization"] = relationship("Organization")
    tool_group: Mapped[Optional["ToolGroup"]] = relationship("ToolGroup")

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_org_api_key_name"
        ),
        Index("idx_api_keys_active", "is_active"),
        Index("idx_api_keys_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"

    @property
    def is_expired(self) -> bool:
        """Check if API key is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    @staticmethod
    def generate_key() -> tuple[str, str]:
        """
        Generate a new API key.

        Returns:
            tuple: (full_key, key_prefix)
                - full_key: The complete API key to show to user ONCE
                - key_prefix: First 8 chars for display in UI

        Format: mcphub_sk_{32_random_chars}
        Example: mcphub_sk_7f8a9b2c4d5e6f1a8b3c9d2e4f5a6b7c
        """
        # Generate secure random string (32 chars = 160 bits of entropy)
        random_part = secrets.token_urlsafe(24)[:32]  # URL-safe base64, truncated to 32 chars
        full_key = f"mcphub_sk_{random_part}"
        key_prefix = full_key[:20]  # mcphub_sk_abc12345
        return full_key, key_prefix

    @staticmethod
    def hash_key(key: str) -> str:
        """
        Hash an API key using bcrypt.

        Args:
            key: The plaintext API key

        Returns:
            str: Bcrypt hash
        """
        import bcrypt
        return bcrypt.hashpw(key.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_key(self, key: str) -> bool:
        """
        Verify if a plaintext key matches this API key's hash.

        Args:
            key: The plaintext API key to verify

        Returns:
            bool: True if key matches, False otherwise
        """
        import bcrypt
        try:
            return bcrypt.checkpw(key.encode('utf-8'), self.key_hash.encode('utf-8'))
        except Exception:
            return False

    def has_scope(self, scope: str) -> bool:
        """
        Check if this API key has a specific scope.

        Args:
            scope: The scope to check (e.g., "tools:execute")

        Returns:
            bool: True if key has this scope or admin scope
        """
        return scope in self.scopes or APIKeyScope.ADMIN.value in self.scopes
