"""
Subscription service for Cloud SaaS MVP.

Handles subscription validation, user limit enforcement, and tier management.
Ultra-simplified for MVP - no LLM quota tracking.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
from ..models.organization import Organization, OrganizationMember


class SubscriptionError(Exception):
    """Base exception for subscription-related errors."""
    pass


class SubscriptionNotFoundError(SubscriptionError):
    """Raised when subscription is not found."""
    pass


class SubscriptionInactiveError(SubscriptionError):
    """Raised when subscription is not active."""
    pass


class UserLimitExceededError(SubscriptionError):
    """Raised when user limit is exceeded."""
    pass


class SubscriptionService:
    """
    Service for managing Cloud SaaS subscriptions.

    Simplified for MVP:
    - 2 tiers only (Individual/Team)
    - No LLM quota tracking
    - User limit enforcement only
    """

    @staticmethod
    async def get_subscription_by_organization(
        session: AsyncSession,
        organization_id: UUID
    ) -> Optional[Subscription]:
        """
        Get subscription for an organization.

        Args:
            session: Database session
            organization_id: Organization UUID

        Returns:
            Subscription or None if not found
        """
        result = await session.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .options(joinedload(Subscription.organization))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_subscription(
        session: AsyncSession,
        organization_id: UUID
    ) -> Subscription:
        """
        Get active subscription for an organization.

        Args:
            session: Database session
            organization_id: Organization UUID

        Returns:
            Active subscription

        Raises:
            SubscriptionNotFoundError: If no subscription found
            SubscriptionInactiveError: If subscription is not active
        """
        subscription = await SubscriptionService.get_subscription_by_organization(
            session,
            organization_id
        )

        if not subscription:
            raise SubscriptionNotFoundError(
                f"No subscription found for organization {organization_id}"
            )

        if not subscription.is_active:
            raise SubscriptionInactiveError(
                f"Subscription is {subscription.status.value} (expired: {subscription.current_period_end})"
            )

        return subscription

    @staticmethod
    async def validate_user_limit(
        session: AsyncSession,
        organization_id: UUID,
        additional_users: int = 1
    ) -> bool:
        """
        Validate if organization can add more users without exceeding limit.

        Args:
            session: Database session
            organization_id: Organization UUID
            additional_users: Number of users to add (default: 1)

        Returns:
            True if within limit

        Raises:
            SubscriptionNotFoundError: If no subscription found
            SubscriptionInactiveError: If subscription is not active
            UserLimitExceededError: If adding users would exceed limit
        """
        subscription = await SubscriptionService.get_active_subscription(
            session,
            organization_id
        )

        # Count current members
        result = await session.execute(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
        )
        current_user_count = len(result.scalars().all())

        # Check if adding users would exceed limit (0 = unlimited)
        if subscription.max_users > 0 and current_user_count + additional_users > subscription.max_users:
            raise UserLimitExceededError(
                f"User limit exceeded: {current_user_count + additional_users}/{subscription.max_users} "
                f"(tier: {subscription.tier.value})"
            )

        return True

    @staticmethod
    async def can_add_user(
        session: AsyncSession,
        organization_id: UUID
    ) -> bool:
        """
        Check if organization can add another user (non-raising version).

        Args:
            session: Database session
            organization_id: Organization UUID

        Returns:
            True if can add user, False otherwise
        """
        try:
            return await SubscriptionService.validate_user_limit(session, organization_id)
        except (SubscriptionError, Exception):
            return False

    @staticmethod
    async def get_subscription_limits(
        session: AsyncSession,
        organization_id: UUID
    ) -> dict:
        """
        Get subscription limits and current usage.

        Args:
            session: Database session
            organization_id: Organization UUID

        Returns:
            Dictionary with limits and usage
        """
        subscription = await SubscriptionService.get_active_subscription(
            session,
            organization_id
        )

        # Count current members
        result = await session.execute(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
        )
        current_users = len(result.scalars().all())

        return {
            "tier": subscription.tier.value,
            "status": subscription.status.value,
            "users": {
                "current": current_users,
                "max": subscription.max_users if subscription.max_users > 0 else None,
                "available": (subscription.max_users - current_users) if subscription.max_users > 0 else None
            },
            "features": subscription.get_tier_limits(),
            "billing": {
                "current_period_start": subscription.current_period_start.isoformat(),
                "current_period_end": subscription.current_period_end.isoformat(),
                "trial": subscription.is_trial,
                "cancel_at_period_end": subscription.cancel_at_period_end
            }
        }

    @staticmethod
    async def create_subscription(
        session: AsyncSession,
        organization_id: UUID,
        tier: SubscriptionTier,
        lemonsqueezy_subscription_id: str,
        current_period_start: datetime,
        current_period_end: datetime,
        lemonsqueezy_customer_id: Optional[str] = None,
        lemonsqueezy_variant_id: Optional[str] = None,
        trial_ends_at: Optional[datetime] = None
    ) -> Subscription:
        """
        Create new subscription for organization.

        Args:
            session: Database session
            organization_id: Organization UUID
            tier: Subscription tier (Individual/Team)
            lemonsqueezy_subscription_id: LemonSqueezy subscription ID
            current_period_start: Billing period start
            current_period_end: Billing period end
            lemonsqueezy_customer_id: LemonSqueezy customer ID
            lemonsqueezy_variant_id: LemonSqueezy variant ID
            trial_ends_at: Trial end date (optional)

        Returns:
            Created subscription
        """
        # Set max_users based on tier (0 = unlimited for Team)
        max_users = 1 if tier == SubscriptionTier.INDIVIDUAL else 0

        subscription = Subscription(
            organization_id=organization_id,
            tier=tier,
            status=SubscriptionStatus.TRIALING if trial_ends_at else SubscriptionStatus.ACTIVE,
            max_users=max_users,
            lemonsqueezy_subscription_id=lemonsqueezy_subscription_id,
            lemonsqueezy_customer_id=lemonsqueezy_customer_id,
            lemonsqueezy_variant_id=lemonsqueezy_variant_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            trial_ends_at=trial_ends_at,
            cancel_at_period_end=False
        )

        session.add(subscription)
        await session.flush()
        await session.refresh(subscription)

        return subscription

    @staticmethod
    async def update_subscription_status(
        session: AsyncSession,
        subscription_id: UUID,
        status: SubscriptionStatus
    ) -> Subscription:
        """
        Update subscription status.

        Args:
            session: Database session
            subscription_id: Subscription UUID
            status: New status

        Returns:
            Updated subscription
        """
        result = await session.execute(
            select(Subscription)
            .where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one()

        subscription.status = status
        await session.flush()
        await session.refresh(subscription)

        return subscription

    @staticmethod
    async def cancel_subscription(
        session: AsyncSession,
        subscription_id: UUID,
        cancel_at_period_end: bool = True
    ) -> Subscription:
        """
        Cancel subscription.

        Args:
            session: Database session
            subscription_id: Subscription UUID
            cancel_at_period_end: If True, cancel at period end; if False, cancel immediately

        Returns:
            Updated subscription
        """
        result = await session.execute(
            select(Subscription)
            .where(Subscription.id == subscription_id)
        )
        subscription = result.scalar_one()

        subscription.cancel_at_period_end = cancel_at_period_end
        subscription.cancelled_at = datetime.now(datetime.now().astimezone().tzinfo)

        if not cancel_at_period_end:
            subscription.status = SubscriptionStatus.CANCELLED

        await session.flush()
        await session.refresh(subscription)

        return subscription
