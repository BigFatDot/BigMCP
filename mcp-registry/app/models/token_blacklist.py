"""
Token blacklist model for JWT revocation.

Stores blacklisted JWT IDs (JTI) to enable token revocation on logout,
password change, or admin action.
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import UUIDType


class BlacklistReason(str, enum.Enum):
    """Reason for token blacklisting."""
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    ADMIN_REVOKE = "admin_revoke"
    SECURITY_BREACH = "security_breach"


class TokenBlacklist(Base, UUIDMixin, TimestampMixin):
    """
    Blacklisted JWT tokens.

    Used to invalidate tokens before their natural expiration.
    Tokens are identified by their JTI (JWT ID) claim.
    """

    __tablename__ = "token_blacklist"

    # JWT identifier (unique per token)
    jti: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True
    )

    # User who owned the token
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUIDType,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Token type (access or refresh)
    token_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="access"
    )

    # When the token expires (for auto-cleanup)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    # Reason for blacklisting
    reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=BlacklistReason.LOGOUT.value
    )

    # Additional indexes for cleanup queries
    __table_args__ = (
        Index("idx_token_blacklist_expires_at", "expires_at"),
        Index("idx_token_blacklist_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<TokenBlacklist(jti={self.jti[:8]}..., reason={self.reason})>"

    @property
    def is_expired(self) -> bool:
        """Check if the original token has expired (safe to delete)."""
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)
