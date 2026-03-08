"""
License models for open-core enforcement.

Supports:
- License key validation (online and offline)
- Feature entitlements (oauth, sso, webhooks, etc.)
- Resource limits (users, servers, contexts, etc.)
- Multiple editions (Community, Professional, Enterprise)
- Multiple deployment types (Cloud, Self-hosted)
"""

import enum
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import String, Integer, LargeBinary, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class LicenseEdition(str, enum.Enum):
    """
    License edition tiers.

    - COMMUNITY: Free, self-hosted, single-user only
    - PROFESSIONAL: Paid, multi-user, organizations, RBAC
    - ENTERPRISE: Paid, SSO, audit, AI orchestration, LLM dedicated
    """
    COMMUNITY = "community"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class LicenseType(str, enum.Enum):
    """
    Deployment type for the license.

    - CLOUD: BigMCP hosted service (SaaS)
    - SELF_HOSTED: Customer-hosted deployment
    """
    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"


class LicenseStatus(str, enum.Enum):
    """
    Current status of the license.

    - TRIAL: Trial period (time-limited)
    - ACTIVE: License is valid and active
    - EXPIRED: License has expired
    - SUSPENDED: License temporarily suspended (payment issue, violation, etc.)
    - REVOKED: License permanently revoked
    """
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class License(Base, UUIDMixin, TimestampMixin):
    """
    License model for open-core enforcement.

    Each license:
    - Grants access to specific features and resource limits
    - Can be validated online (cloud) or offline (self-hosted)
    - Tied to an organization (Professional/Enterprise) or standalone (Community)
    - Tracks installation for offline validation
    """

    __tablename__ = "licenses"

    # License key (JWT token for Enterprise, format BIGMCP-XXXX for others)
    license_key: Mapped[str] = mapped_column(
        String(1000),
        unique=True,
        nullable=False,
        index=True
    )

    # Edition & Type
    edition: Mapped[LicenseEdition] = mapped_column(
        SQLEnum(LicenseEdition, name="license_edition"),
        nullable=False,
        index=True
    )
    license_type: Mapped[LicenseType] = mapped_column(
        SQLEnum(LicenseType, name="license_type"),
        nullable=False
    )
    status: Mapped[LicenseStatus] = mapped_column(
        SQLEnum(LicenseStatus, name="license_status"),
        nullable=False,
        default=LicenseStatus.ACTIVE,
        index=True
    )

    # Organization link (nullable for Community edition)
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Resource limits
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_servers: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_api_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_contexts: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_compositions: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # Feature entitlements (JSONB for flexibility)
    # Example: {"oauth": true, "sso": false, "webhooks": true, "ai_orchestration": false}
    features: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=dict
    )

    # Validity period
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True  # None = perpetual license
    )

    # Offline validation (for air-gapped deployments)
    # Contains encrypted license data and RSA signature for offline validation
    license_data_encrypted: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True
    )
    signature: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True
    )

    # Installation tracking (for self-hosted deployments)
    # Unique identifier for the installation (machine fingerprint)
    installation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    # Customer metadata
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Billing reference (for integration with Stripe, etc.)
    billing_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # LemonSqueezy order tracking (for Enterprise purchases)
    lemonsqueezy_order_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True
    )
    lemonsqueezy_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Additional metadata (JSONB) - using license_metadata to avoid conflict with SQLAlchemy metadata
    license_metadata: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=dict
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="licenses",
        foreign_keys=[organization_id]
    )

    validations: Mapped[List["LicenseValidation"]] = relationship(
        "LicenseValidation",
        back_populates="license",
        cascade="all, delete-orphan",
        order_by="LicenseValidation.validated_at.desc()"
    )

    # Table indexes for performance
    __table_args__ = (
        Index("idx_license_org_status", organization_id, status),
        Index("idx_license_installation", installation_id, status),
        Index("idx_license_expires", expires_at),
    )

    def __repr__(self) -> str:
        return (
            f"<License(id={self.id}, key={self.license_key[:20]}..., "
            f"edition={self.edition}, status={self.status})>"
        )

    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid."""
        if self.status != LicenseStatus.ACTIVE:
            return False

        if self.expires_at and self.expires_at < datetime.now():
            return False

        return True

    @property
    def is_expired(self) -> bool:
        """Check if license has expired."""
        if self.expires_at and self.expires_at < datetime.now():
            return True
        return False

    def has_feature(self, feature_key: str) -> bool:
        """
        Check if license grants access to a specific feature.

        Args:
            feature_key: Feature identifier (e.g., "oauth", "sso", "webhooks")

        Returns:
            True if feature is enabled, False otherwise
        """
        return self.features.get(feature_key, False) is True

    def check_limit(self, limit_key: str, current_value: int) -> bool:
        """
        Check if current usage is within license limits.

        Args:
            limit_key: Limit identifier ("max_users", "max_servers", etc.)
            current_value: Current usage count

        Returns:
            True if within limits, False if exceeded
        """
        limit_value = getattr(self, limit_key, None)
        if limit_value is None:
            return True  # No limit

        return current_value < limit_value


class LicenseValidation(Base, UUIDMixin, TimestampMixin):
    """
    License validation audit trail.

    Records each validation attempt (both successful and failed)
    for monitoring and compliance purposes.
    """

    __tablename__ = "license_validations"

    # License reference
    license_id: Mapped[UUID] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Validation timestamp
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        index=True
    )

    # Validation result
    validation_result: Mapped[bool] = mapped_column(
        nullable=False,
        index=True
    )
    validation_reason: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )

    # Installation tracking
    installation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )

    # Request metadata
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional context (JSONB)
    context: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=dict
    )

    # Relationships
    license: Mapped["License"] = relationship(
        "License",
        back_populates="validations"
    )

    # Table indexes for performance
    __table_args__ = (
        Index("idx_validation_license_time", license_id, validated_at),
        Index("idx_validation_installation", installation_id, validated_at),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseValidation(id={self.id}, license_id={self.license_id}, "
            f"result={self.validation_result}, at={self.validated_at})>"
        )
