"""
Password Reset Token model for secure password recovery.

Stores hashed tokens with expiration for email-based password reset flow.
"""

import secrets
import hashlib
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import String, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..core.config import settings


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    """
    Password Reset Token for secure password recovery.

    Tokens are hashed before storage (SHA-256) for security.
    Each token can only be used once and expires after a configurable period.
    """

    __tablename__ = "password_reset_tokens"

    # User reference
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who requested password reset"
    )

    # Token (hashed)
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the reset token"
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token expiration timestamp"
    )

    # Usage tracking
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the token was used (None if not used)"
    )

    # Request metadata
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address that requested the reset"
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="User agent that requested the reset"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_reset_tokens")

    # Indexes
    __table_args__ = (
        Index("idx_password_reset_user_expires", "user_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, used={self.used_at is not None})>"

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        now = datetime.utcnow()
        expires = self.expires_at.replace(tzinfo=None) if self.expires_at.tzinfo else self.expires_at
        return now > expires

    @property
    def is_used(self) -> bool:
        """Check if token has already been used."""
        return self.used_at is not None

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)."""
        return not self.is_expired and not self.is_used

    def mark_used(self) -> None:
        """Mark token as used."""
        self.used_at = datetime.utcnow()

    @classmethod
    def create_token(
        cls,
        user_id: UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expire_hours: Optional[int] = None
    ) -> tuple["PasswordResetToken", str]:
        """
        Create a new password reset token.

        Returns:
            tuple: (PasswordResetToken instance, plaintext_token)
                - The instance should be added to session
                - The plaintext_token should be sent to user via email
        """
        # Generate secure token
        plaintext_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plaintext_token.encode('utf-8')).hexdigest()

        # Calculate expiration
        hours = expire_hours or settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        expires_at = datetime.utcnow() + timedelta(hours=hours)

        # Create instance
        instance = cls(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent and len(user_agent) > 500 else user_agent
        )

        return instance, plaintext_token

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash a plaintext token for comparison.

        Args:
            token: Plaintext reset token

        Returns:
            str: SHA-256 hash
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
