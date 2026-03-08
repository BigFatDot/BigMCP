"""
User Credentials Model - Personal credentials per user per MCP server.

Allows users to configure their own credentials for each MCP server.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import String, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class UserCredential(Base, UUIDMixin, TimestampMixin):
    """
    User-specific credentials for MCP servers.

    Each user can configure their own credentials for each MCP server.
    These credentials override organization-level credentials.

    Example:
        User Alice provides her personal OpenAI API key for the openai-mcp server.
        This key is used only when Alice uses the server, not for other users.
    """

    __tablename__ = "user_credentials"

    # Relationships
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns these credentials"
    )

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="MCP server these credentials are for"
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization (for multi-tenancy)"
    )

    # Encrypted credentials
    credentials_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Encrypted JSON containing environment variables"
    )

    # Metadata
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional name for this credential set (e.g., 'My Personal OpenAI Key')"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this credential set is currently active"
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Last time these credentials were used"
    )

    # Validation metadata (optional)
    is_validated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether credentials have been validated by testing"
    )

    validated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When credentials were last validated"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="credentials")
    server: Mapped["MCPServer"] = relationship("MCPServer")
    organization: Mapped["Organization"] = relationship("Organization")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "server_id",
            name="uq_user_server_credentials"
        ),
    )

    def __repr__(self) -> str:
        return f"<UserCredential(user={self.user_id}, server={self.server_id})>"

    @property
    def credentials(self) -> dict:
        """Decrypt and return credentials."""
        from ..core.secrets_manager import secrets_manager
        return secrets_manager.decrypt(self.credentials_encrypted)

    @credentials.setter
    def credentials(self, value: dict):
        """Encrypt and store credentials."""
        from ..core.secrets_manager import secrets_manager
        self.credentials_encrypted = secrets_manager.encrypt(value)


class OrganizationCredential(Base, UUIDMixin, TimestampMixin):
    """
    Organization-level shared credentials for MCP servers.

    Configured by administrators, these credentials are:
    - Shared across all users in the organization
    - Hidden from regular users (only admins can view/edit)
    - Used as fallback when user doesn't have personal credentials

    Example:
        Organization provides a shared OpenAI API key for all employees.
        Users can override with their personal key if they want.
    """

    __tablename__ = "organization_credentials"

    # Relationships
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization that owns these credentials"
    )

    server_id: Mapped[UUID] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="MCP server these credentials are for"
    )

    # Encrypted credentials
    credentials_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Encrypted JSON containing environment variables"
    )

    # Metadata
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name for this credential set (e.g., 'Company OpenAI Account')"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Description (e.g., 'Shared account for all employees')"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this credential set is currently active"
    )

    # Visibility control
    visible_to_users: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="If True, users can see that org credentials exist (but not values)"
    )

    # Usage tracking
    usage_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Number of times these credentials have been used"
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Last time these credentials were used"
    )

    # Audit
    created_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who created these credentials"
    )

    updated_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Admin who last updated these credentials"
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="credentials"
    )
    server: Mapped["MCPServer"] = relationship("MCPServer")
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by]
    )
    updater: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[updated_by]
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "server_id",
            name="uq_org_server_credentials"
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationCredential(org={self.organization_id}, server={self.server_id})>"

    @property
    def credentials(self) -> dict:
        """Decrypt and return credentials."""
        from ..core.secrets_manager import secrets_manager
        return secrets_manager.decrypt(self.credentials_encrypted)

    @credentials.setter
    def credentials(self, value: dict):
        """Encrypt and store credentials."""
        from ..core.secrets_manager import secrets_manager
        self.credentials_encrypted = secrets_manager.encrypt(value)
