"""
Subscription models for Cloud SaaS.

Ultra-simplified model for Individual (€4.99/month) and Team (€4.99/month + €4.99/user) tiers.
No LLM quota tracking - AI features are unlimited and cost negligible (€0.0004/month).
"""

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, UUIDMixin, TimestampMixin
from ..db.types import JSONType


class SubscriptionTier(str, enum.Enum):
    """
    Subscription tier for Cloud SaaS.

    - INDIVIDUAL: €4.99/month, 1 user, unlimited AI features
    - TEAM: €4.99/month + €4.99/user/month, unlimited users, unlimited AI features
    """
    INDIVIDUAL = "individual"
    TEAM = "team"


class SubscriptionStatus(str, enum.Enum):
    """
    Current status of the subscription.

    - TRIALING: Free trial period
    - ACTIVE: Subscription is active and paid
    - PAST_DUE: Payment failed, grace period
    - CANCELLED: Subscription cancelled, access until period end
    - EXPIRED: Subscription expired, no access
    """
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Subscription(Base, UUIDMixin, TimestampMixin):
    """
    Cloud SaaS subscription model.

    Simplified for MVP:
    - 2 tiers only (Individual/Team)
    - No LLM quota tracking (AI features unlimited)
    - User limit enforcement only (1 for Individual, 0=unlimited for Team)
    - LemonSqueezy billing integration
    """

    __tablename__ = "subscriptions"

    # Tier & Status
    # Note: values_callable ensures SQLAlchemy uses enum VALUES ('individual', 'team')
    # instead of enum NAMES (INDIVIDUAL, TEAM) to match PostgreSQL storage
    tier: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(
            SubscriptionTier,
            name="subscription_tier",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SQLEnum(
            SubscriptionStatus,
            name="subscription_status",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
        index=True
    )

    # Organization link (nullable for Individual tier)
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        unique=True  # One subscription per organization
    )

    # Resource limits (ONLY user limit - no LLM quotas!)
    # 0 = unlimited (Team), 1 = Individual
    max_users: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1
    )

    # LemonSqueezy billing
    lemonsqueezy_subscription_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    lemonsqueezy_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    lemonsqueezy_variant_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Billing period
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    # Trial period (optional)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Cancellation tracking
    cancel_at_period_end: Mapped[bool] = mapped_column(
        nullable=False,
        default=False
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Additional metadata (JSONB for flexibility)
    # Example: {"plan_name": "Team Annual", "discount_code": "LAUNCH50"}
    # Note: Using subscription_metadata to avoid conflict with SQLAlchemy's metadata
    subscription_metadata: Mapped[dict] = mapped_column(
        JSONType,
        nullable=False,
        default=dict
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="subscription",
        foreign_keys=[organization_id]
    )

    # Table indexes for performance
    __table_args__ = (
        Index("idx_subscription_org_status", organization_id, status),
        Index("idx_subscription_lemonsqueezy", lemonsqueezy_subscription_id, status),
        Index("idx_subscription_period_end", current_period_end),
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription(id={self.id}, tier={self.tier}, "
            f"status={self.status}, org_id={self.organization_id})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active (not expired)."""
        if self.status == SubscriptionStatus.EXPIRED:
            return False

        # Check if current period has ended
        if self.current_period_end < datetime.now(self.current_period_end.tzinfo):
            return False

        return self.status in [
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.CANCELLED  # Still active until period end
        ]

    @property
    def is_trial(self) -> bool:
        """Check if subscription is in trial period."""
        if self.status != SubscriptionStatus.TRIALING:
            return False

        if self.trial_ends_at is None:
            return False

        return self.trial_ends_at > datetime.now(self.trial_ends_at.tzinfo)

    def can_add_user(self, current_user_count: int) -> bool:
        """
        Check if subscription allows adding another user.

        Args:
            current_user_count: Current number of users in organization

        Returns:
            True if can add user, False if limit reached
        """
        if self.max_users == 0:
            return True  # 0 = unlimited
        return current_user_count < self.max_users

    def get_tier_limits(self) -> dict:
        """
        Get all limits for current tier.

        Returns:
            Dictionary with tier limits
        """
        return {
            "tier": self.tier.value,
            "max_users": self.max_users,
            "unlimited_ai_features": True,  # Always True - no LLM quotas!
            "unlimited_semantic_search": True,
            "unlimited_compositions": True,
            "marketplace_access": True,
            "organizations": self.tier == SubscriptionTier.TEAM,
            "rbac": self.tier == SubscriptionTier.TEAM,
            "oauth": self.tier == SubscriptionTier.TEAM,
            "team_credentials": self.tier == SubscriptionTier.TEAM,
        }
