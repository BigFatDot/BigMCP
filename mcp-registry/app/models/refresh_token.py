"""
Refresh Token model for per-device session management.

Stores refresh tokens to enable:
- Per-device session tracking
- Token rotation (one active token per device)
- Session revocation (logout from specific devices)
- Session listing (view active sessions)
"""

import secrets
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import String, ForeignKey, Boolean, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin


class RefreshToken(Base, UUIDMixin, TimestampMixin):
    """
    Refresh Token for per-device session management.

    Each refresh token represents an active login session on a specific device.
    When a user refreshes their token, the old token is invalidated and a new
    one is created (token rotation).

    This enables:
    - Per-device session management (view/revoke sessions)
    - Token rotation for enhanced security
    - Forced logout from all devices
    - Activity tracking per session
    """

    __tablename__ = "refresh_tokens"

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this refresh token"
    )

    # Token data
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="SHA-256 hash of the refresh token (we don't store plaintext)"
    )

    token_family: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Token family ID for detecting token reuse attacks"
    )

    # Device identification
    device_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Unique device identifier (hash of user_agent + fingerprint)"
    )

    device_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable device name (e.g., 'Chrome on MacOS')"
    )

    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Full user agent string"
    )

    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address when token was created (IPv4 or IPv6)"
    )

    # Status and lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Whether this token is still valid"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Expiration date of this refresh token"
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this token was used to refresh"
    )

    last_used_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address from last use"
    )

    # Revocation info
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this token was revoked (if applicable)"
    )

    revoked_reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Reason for revocation (logout, rotation, security)"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    # Indexes
    __table_args__ = (
        Index("idx_refresh_tokens_user_active", "user_id", "is_active"),
        Index("idx_refresh_tokens_user_device", "user_id", "device_id"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, device={self.device_name})>"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    def revoke(self, reason: str = "user_logout"):
        """
        Revoke this refresh token.

        Args:
            reason: Reason for revocation
        """
        self.is_active = False
        self.revoked_at = datetime.utcnow()
        self.revoked_reason = reason

    @staticmethod
    def generate_token() -> tuple[str, str]:
        """
        Generate a new refresh token.

        Returns:
            tuple: (plaintext_token, token_hash)
                - plaintext_token: The token to send to client (shown once)
                - token_hash: SHA-256 hash to store in database
        """
        import hashlib

        # Generate secure random token (256 bits of entropy)
        plaintext = secrets.token_urlsafe(32)

        # Hash with SHA-256 for storage
        token_hash = hashlib.sha256(plaintext.encode('utf-8')).hexdigest()

        return plaintext, token_hash

    @staticmethod
    def generate_family_id() -> str:
        """
        Generate a token family ID for token rotation tracking.

        Token families help detect token reuse attacks:
        - When a token is refreshed, the new token inherits the family ID
        - If an old token from the same family is used, all tokens
          in that family are revoked (potential attack detected)

        Returns:
            str: Random family ID (32 chars)
        """
        return secrets.token_urlsafe(24)[:32]

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash a refresh token for comparison.

        Args:
            token: Plaintext refresh token

        Returns:
            str: SHA-256 hash
        """
        import hashlib
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_device_id(user_agent: str, fingerprint: str = "") -> str:
        """
        Generate a device identifier from user agent and optional fingerprint.

        Args:
            user_agent: HTTP User-Agent header
            fingerprint: Optional browser fingerprint

        Returns:
            str: Device ID hash (64 chars)
        """
        import hashlib
        combined = f"{user_agent}:{fingerprint}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    @staticmethod
    def parse_device_name(user_agent: str) -> str:
        """
        Parse a human-readable device name from user agent.

        Args:
            user_agent: HTTP User-Agent header

        Returns:
            str: Human-readable device name
        """
        ua = user_agent.lower()

        # Detect browser
        browser = "Unknown Browser"
        if "chrome" in ua and "safari" in ua and "edg" not in ua:
            browser = "Chrome"
        elif "firefox" in ua:
            browser = "Firefox"
        elif "safari" in ua and "chrome" not in ua:
            browser = "Safari"
        elif "edg" in ua:
            browser = "Edge"
        elif "opera" in ua or "opr" in ua:
            browser = "Opera"

        # Detect OS
        os_name = "Unknown OS"
        if "windows" in ua:
            os_name = "Windows"
        elif "mac os" in ua or "macos" in ua:
            os_name = "macOS"
        elif "linux" in ua:
            os_name = "Linux"
        elif "android" in ua:
            os_name = "Android"
        elif "iphone" in ua or "ipad" in ua:
            os_name = "iOS"

        return f"{browser} on {os_name}"
