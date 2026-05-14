"""
OAuthSession model — Connected-app tracking (N2.4 / Story H).

Each row records one OAuth-issued JWT pair (access + refresh) so the user
can list "connected apps" and revoke a specific client without burning
their entire session set.

Design note (Design C):
    The ``refresh_tokens`` table is currently a ghost — no code path
    actually inserts rows into it. We don't try to fix that here. Instead
    this dedicated table tracks OAuth-grant sessions only, leaving the
    classic browser-login path untouched. A later "DB-backed kill switch
    for human sessions" chantier can revisit ``refresh_tokens``.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, ForeignKey, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin


class OAuthSession(Base, UUIDMixin, TimestampMixin):
    """One persisted OAuth grant (per user × client × token issuance)."""

    __tablename__ = "oauth_sessions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who consented to this OAuth grant",
    )

    oauth_client_id: Mapped[UUID] = mapped_column(
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="OAuth client (Claude, custom DCR/CIMD client, etc.)",
    )

    organization_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Organization context the grant was issued under",
    )

    # JWT JTI captured at issuance — lets us correlate with token blacklist
    # and audit logs (we don't store the JWT itself).
    access_token_jti: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="JTI of the access token issued at grant time",
    )
    refresh_token_jti: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="JTI of the refresh token issued at grant time",
    )

    # Context captured at issuance
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4/IPv6 from which the grant was completed",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User-Agent header at grant time",
    )

    # Lifecycle
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time a refresh_token grant was seen for this session",
    )

    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="When this session was revoked (NULL = active)",
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Why the session was revoked (user_revoke, admin_revoke, ...)",
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    oauth_client = relationship("OAuthClient", foreign_keys=[oauth_client_id])
    organization = relationship("Organization", foreign_keys=[organization_id])

    __table_args__ = (
        Index(
            "ix_oauth_sessions_user_active",
            "user_id",
            "revoked_at",
        ),
        Index(
            "ix_oauth_sessions_user_client",
            "user_id",
            "oauth_client_id",
        ),
    )

    def revoke(self, reason: str = "user_revoke") -> None:
        """Mark this session as revoked."""
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return (
            f"<OAuthSession(id={self.id}, user_id={self.user_id}, "
            f"client={self.oauth_client_id}, active={self.is_active})>"
        )
