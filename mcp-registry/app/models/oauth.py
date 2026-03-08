"""
OAuth 2.0 models for Claude Desktop integration.

Implements Authorization Code Flow for secure third-party access.
"""

import enum
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import String, Text, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class OAuthClient(Base, UUIDMixin, TimestampMixin):
    """
    OAuth 2.0 Client registration (e.g., Claude Desktop).

    Represents a registered application that can request access
    to user resources via OAuth 2.0 Authorization Code Flow.

    Example:
        Claude Desktop registers as a client with:
        - client_id: auto-generated UUID
        - client_secret: auto-generated secure secret
        - redirect_uri: "https://claude.ai/api/oauth/callback"
        - name: "Claude Desktop"
    """

    __tablename__ = "oauth_clients"

    # Client credentials
    client_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="OAuth Client ID (public identifier)"
    )

    client_secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="OAuth Client Secret (hashed)"
    )

    # Client information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Client application name (e.g., 'Claude Desktop')"
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Description of the client application"
    )

    # Redirect URIs (JSON array of allowed URIs)
    redirect_uris: Mapped[list] = mapped_column(
        JSONType,
        nullable=False,
        comment="Allowed redirect URIs for this client"
    )

    # Scopes
    allowed_scopes: Mapped[list] = mapped_column(
        JSONType,
        default=["mcp:execute", "mcp:read"],
        nullable=False,
        comment="Scopes this client is allowed to request"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this client is currently active"
    )

    is_trusted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Trusted clients skip consent screen"
    )

    # Metadata
    extra_metadata: Mapped[dict] = mapped_column(
        JSONType,
        default={},
        nullable=False,
        comment="Additional client metadata"
    )

    # Relationships
    authorization_codes: Mapped[list["AuthorizationCode"]] = relationship(
        "AuthorizationCode",
        back_populates="client",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<OAuthClient(id={self.id}, name={self.name}, client_id={self.client_id})>"


class AuthorizationCode(Base, UUIDMixin, TimestampMixin):
    """
    Temporary authorization code issued during OAuth flow.

    Short-lived code (5 minutes) exchanged for access token.
    One-time use only (deleted after exchange).

    Flow:
        1. User authorizes → Server creates AuthorizationCode
        2. Client receives code via redirect
        3. Client exchanges code for token → Code deleted
    """

    __tablename__ = "authorization_codes"

    # Code
    code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Authorization code (random secure string)"
    )

    # Client and User
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="OAuth client this code was issued to"
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who authorized this code"
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization context for this authorization"
    )

    # OAuth parameters
    redirect_uri: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Redirect URI used in authorization request"
    )

    scopes: Mapped[list] = mapped_column(
        JSONType,
        default=["mcp:execute"],
        nullable=False,
        comment="Granted scopes"
    )

    # PKCE support (optional but recommended)
    code_challenge: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="PKCE code challenge (for public clients)"
    )

    code_challenge_method: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="PKCE challenge method (S256 or plain)"
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="When this code expires (typically 5 minutes)"
    )

    # Usage tracking
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether this code has been exchanged for token"
    )

    used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When this code was used (if used)"
    )

    # Relationships
    client: Mapped["OAuthClient"] = relationship("OAuthClient", back_populates="authorization_codes")
    user: Mapped["User"] = relationship("User")
    organization: Mapped["Organization"] = relationship("Organization")

    def is_valid(self) -> bool:
        """Check if this authorization code is still valid."""
        return (
            not self.is_used and
            datetime.utcnow() < self.expires_at
        )

    def __repr__(self) -> str:
        return f"<AuthorizationCode(code={self.code[:8]}..., user_id={self.user_id}, expires_at={self.expires_at})>"
