"""
Marketplace API Key model for authentication.

Supports both Cloud (secondary auth) and Self-hosted (primary auth) users.
"""

import enum
import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index, Boolean
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class DeploymentType(str, enum.Enum):
    """Deployment type for marketplace API usage tracking."""
    CLOUD = "cloud"  # Cloud SaaS users (JWT primary, API key optional)
    SELF_HOSTED_COMMUNITY = "self_hosted_community"  # Free self-hosted
    SELF_HOSTED_ENTERPRISE = "self_hosted_enterprise"  # Paid self-hosted


class MarketplaceAPIKey(Base, UUIDMixin, TimestampMixin):
    """
    Marketplace API key for self-hosted authentication.

    Cloud users use JWT tokens for marketplace access.
    Self-hosted users use API keys (created after registration).

    Security:
    - Keys are prefixed with "mcphub_mk_" for identification
    - Only hashed version stored in database
    - Rate limited to 100 requests/minute (free tier)
    """

    __tablename__ = "marketplace_api_keys"

    # User relationship
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Key details
    key_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User-friendly name (e.g., 'Production Server')"
    )
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA256 hash of the API key"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="First 8 chars of key for identification (mcphub_mk_xxxxxxxx)"
    )

    # Deployment info
    deployment_type: Mapped[DeploymentType] = mapped_column(
        SQLEnum(DeploymentType, name="deployment_type"),
        nullable=False,
        default=DeploymentType.SELF_HOSTED_COMMUNITY,
        index=True
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )
    request_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total requests made with this key"
    )

    # Rate limiting (stored for analytics)
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Requests per minute allowed (free tier: 100)"
    )

    # Metadata
    key_metadata: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=dict,
        comment="Additional info (IP, user agent, etc.)"
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="marketplace_api_keys",
        foreign_keys=[user_id]
    )

    # Table indexes for performance
    __table_args__ = (
        Index("idx_marketplace_key_user_active", user_id, is_active),
        Index("idx_marketplace_key_hash", key_hash),
        Index("idx_marketplace_key_last_used", last_used_at),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketplaceAPIKey(id={self.id}, name={self.key_name}, "
            f"prefix={self.key_prefix}, deployment={self.deployment_type})>"
        )

    @staticmethod
    def generate_api_key() -> str:
        """
        Generate a new marketplace API key.

        Format: mcphub_mk_<32_random_chars>
        Example: mcphub_mk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

        Returns:
            API key string (unhashed)
        """
        random_part = secrets.token_urlsafe(24)  # 32 chars base64
        return f"mcphub_mk_{random_part}"

    @staticmethod
    def hash_key(key: str) -> str:
        """
        Hash an API key for secure storage.

        Args:
            key: Raw API key string

        Returns:
            SHA256 hash of the key
        """
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def get_key_prefix(key: str) -> str:
        """
        Extract displayable prefix from API key.

        Args:
            key: Raw API key string

        Returns:
            First 20 characters (mcphub_mk_xxxxxxxx)
        """
        return key[:20] if len(key) >= 20 else key

    def revoke(self) -> None:
        """Revoke this API key (soft delete)."""
        self.is_active = False
        self.revoked_at = datetime.now(datetime.now().astimezone().tzinfo)

    def record_usage(self) -> None:
        """Record API key usage (call after each request)."""
        self.last_used_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.request_count += 1

    @property
    def is_revoked(self) -> bool:
        """Check if key is revoked."""
        return not self.is_active or self.revoked_at is not None
