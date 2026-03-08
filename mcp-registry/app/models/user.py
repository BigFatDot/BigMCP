"""
User model for authentication and authorization.

Supports multiple auth providers (local, Google, GitHub, SAML).
"""

import enum
from typing import List, Optional
from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class AuthProvider(str, enum.Enum):
    """Authentication provider for user login."""
    LOCAL = "local"  # Email/password
    GOOGLE = "google"  # Google OAuth
    GITHUB = "github"  # GitHub OAuth
    SAML = "saml"  # SAML 2.0 (enterprise SSO)


class User(Base, UUIDMixin, TimestampMixin):
    """
    User model for authentication and authorization.

    Users can:
    - Belong to multiple organizations with different roles
    - Authenticate via multiple providers
    - Have personal preferences and settings
    """

    __tablename__ = "users"

    # Basic info
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Authentication
    auth_provider: Mapped[AuthProvider] = mapped_column(
        String(50),
        nullable=False,
        default=AuthProvider.LOCAL
    )
    auth_provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # null for SSO users

    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether user has verified their email address"
    )

    # Metadata
    preferences: Mapped[dict] = mapped_column(JSONType, default={}, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Session Revocation
    # When set, all tokens issued before this timestamp are invalid
    # Used for: password change, admin revocation, security incidents
    tokens_revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last bulk token revocation. Tokens issued before this are invalid."
    )

    # MFA/TOTP Fields
    # Implements RFC 6238 (TOTP) two-factor authentication
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether MFA is enabled for this user"
    )
    mfa_secret: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Encrypted TOTP secret (Fernet encrypted)"
    )
    mfa_backup_codes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted JSON array of backup codes"
    )
    mfa_enrolled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When MFA was enabled for this user"
    )

    # Relationships
    organization_memberships: Mapped[List["OrganizationMember"]] = relationship(
        "OrganizationMember",
        foreign_keys="OrganizationMember.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    credentials: Mapped[List["UserCredential"]] = relationship(
        "UserCredential",
        foreign_keys="UserCredential.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    api_keys: Mapped[List["APIKey"]] = relationship(
        "APIKey",
        foreign_keys="APIKey.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    credential_setup_tokens: Mapped[List["CredentialSetupToken"]] = relationship(
        "CredentialSetupToken",
        foreign_keys="CredentialSetupToken.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    marketplace_api_keys: Mapped[List["MarketplaceAPIKey"]] = relationship(
        "MarketplaceAPIKey",
        foreign_keys="MarketplaceAPIKey.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        foreign_keys="RefreshToken.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
        foreign_keys="PasswordResetToken.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    email_verification_tokens: Mapped[List["EmailVerificationToken"]] = relationship(
        "EmailVerificationToken",
        foreign_keys="EmailVerificationToken.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, provider={self.auth_provider})>"

    @property
    def is_sso(self) -> bool:
        """Check if user uses SSO authentication."""
        return self.auth_provider != AuthProvider.LOCAL

    @property
    def organizations(self) -> List["Organization"]:
        """Get all organizations this user belongs to."""
        return [membership.organization for membership in self.organization_memberships]
