"""
Organization models for multi-tenancy.

Organizations are the top-level entity for multi-tenant isolation.
Each organization owns MCP servers, tools, contexts, and resources.
"""

import enum
from typing import List, Optional
from uuid import UUID

from sqlalchemy import String, Integer, Enum as SQLEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class OrganizationType(str, enum.Enum):
    """Type of organization for different use cases."""
    PERSONAL = "personal"  # Individual user (free tier)
    TEAM = "team"  # Small team (collaboration features)
    ENTERPRISE = "enterprise"  # Enterprise (SSO, advanced features)


class UserRole(str, enum.Enum):
    """User role within an organization."""
    OWNER = "owner"  # Full control, billing access
    ADMIN = "admin"  # Manage resources, members (no billing)
    MEMBER = "member"  # Create/edit own resources
    VIEWER = "viewer"  # Read-only access


class Organization(Base, UUIDMixin, TimestampMixin):
    """
    Organization model for multi-tenant isolation.

    Each organization:
    - Owns MCP servers, tools, contexts, compositions
    - Has members with different roles
    - Has resource limits based on plan
    - Can be personal, team, or enterprise
    """

    __tablename__ = "organizations"

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[OrganizationType] = mapped_column(
        SQLEnum(OrganizationType, name="organization_type"),
        nullable=False,
        default=OrganizationType.PERSONAL
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Settings (JSONB for flexibility)
    settings: Mapped[dict] = mapped_column(JSONType, default={}, nullable=False)

    # Billing & Limits
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    max_contexts: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_tool_bindings: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_api_keys: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_mcp_servers: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Relationships
    members: Mapped[List["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    mcp_servers: Mapped[List["MCPServer"]] = relationship(
        "MCPServer",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    contexts: Mapped[List["Context"]] = relationship(
        "Context",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    credentials: Mapped[List["OrganizationCredential"]] = relationship(
        "OrganizationCredential",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    credential_setup_tokens: Mapped[List["CredentialSetupToken"]] = relationship(
        "CredentialSetupToken",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    licenses: Mapped[List["License"]] = relationship(
        "License",
        back_populates="organization",
        cascade="all, delete-orphan"
    )

    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription",
        back_populates="organization",
        uselist=False  # One-to-one relationship
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name}, type={self.organization_type})>"


class OrganizationMember(Base, UUIDMixin, TimestampMixin):
    """
    Organization membership with role-based permissions.

    Links users to organizations with specific roles.
    """

    __tablename__ = "organization_members"

    # Foreign keys
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Role
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.MEMBER
    )

    # Invitation tracking
    invited_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members"
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="organization_memberships"
    )

    inviter: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[invited_by]
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role={self.role})>"
