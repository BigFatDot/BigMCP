"""
Email Verification Token model for verifying user email addresses.

Stores hashed tokens with expiration for email verification flow.
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


class EmailVerificationToken(Base, UUIDMixin, TimestampMixin):
    """
    Email Verification Token for verifying user email addresses.

    Tokens are hashed before storage (SHA-256) for security.
    Each token can only be used once and expires after a configurable period.
    """

    __tablename__ = "email_verification_tokens"

    # User reference
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who needs email verification"
    )

    # Token (hashed)
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the verification token"
    )

    # Email being verified (in case user changes email)
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Email address being verified"
    )

    # Expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token expiration timestamp"
    )

    # Usage tracking
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the email was verified (None if not verified)"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="email_verification_tokens")

    # Indexes
    __table_args__ = (
        Index("idx_email_verification_user_expires", "user_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<EmailVerificationToken(id={self.id}, user_id={self.user_id}, verified={self.verified_at is not None})>"

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        now = datetime.utcnow()
        expires = self.expires_at.replace(tzinfo=None) if self.expires_at.tzinfo else self.expires_at
        return now > expires

    @property
    def is_verified(self) -> bool:
        """Check if token has already been used."""
        return self.verified_at is not None

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)."""
        return not self.is_expired and not self.is_verified

    def mark_verified(self) -> None:
        """Mark email as verified."""
        self.verified_at = datetime.utcnow()

    @classmethod
    def create_token(
        cls,
        user_id: UUID,
        email: str,
        expire_hours: int = 48
    ) -> tuple["EmailVerificationToken", str]:
        """
        Create a new email verification token.

        Returns:
            tuple: (EmailVerificationToken instance, plaintext_token)
                - The instance should be added to session
                - The plaintext_token should be sent to user via email
        """
        # Generate secure token
        plaintext_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plaintext_token.encode('utf-8')).hexdigest()

        # Calculate expiration (default 48 hours for email verification)
        expires_at = datetime.utcnow() + timedelta(hours=expire_hours)

        # Create instance
        instance = cls(
            user_id=user_id,
            email=email.lower(),
            token_hash=token_hash,
            expires_at=expires_at
        )

        return instance, plaintext_token

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash a plaintext token for comparison.

        Args:
            token: Plaintext verification token

        Returns:
            str: SHA-256 hash
        """
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
