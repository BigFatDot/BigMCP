"""
Feature Gating Middleware - Cloud SaaS Subscription Enforcement.

Provides decorators and dependencies to restrict features based on subscription tier.
"""

from typing import Optional, Callable
from functools import wraps
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionTier
from app.services.subscription_service import (
    SubscriptionService,
    SubscriptionNotFoundError,
    SubscriptionInactiveError,
)
from app.api.dependencies import get_current_user_jwt, _extract_org_id_from_jwt, _resolve_organization


class FeatureGateError(HTTPException):
    """Raised when user doesn't have access to a feature."""

    def __init__(self, feature: str, required_tier: SubscriptionTier):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_access_denied",
                "message": f"This feature requires {required_tier.value} tier subscription",
                "feature": feature,
                "required_tier": required_tier.value,
                "upgrade_url": "/billing/upgrade",
            },
        )


async def get_current_subscription(
    request: Request,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
) -> Subscription:
    """
    Dependency: Get current user's active subscription.

    Raises:
        HTTPException: If no active subscription found.
    """
    # Get user's organization from membership
    if not user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "subscription_required",
                "message": "User has no organization",
                "checkout_url": "/billing/checkout",
            },
        )

    # Resolve organization from JWT context (supports multi-org users)
    membership, organization_id = _resolve_organization(request, user, None)

    # Get organization subscription
    try:
        subscription = await SubscriptionService.get_active_subscription(
            db, organization_id
        )
        return subscription
    except (SubscriptionNotFoundError, SubscriptionInactiveError) as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "subscription_required",
                "message": str(e),
                "checkout_url": "/billing/checkout",
            },
        )


def require_subscription(tier: SubscriptionTier):
    """
    Decorator: Require minimum subscription tier.

    Usage:
        @router.post("/organizations")
        @require_subscription(tier=SubscriptionTier.TEAM)
        async def create_organization(...):
            ...

    Args:
        tier: Minimum subscription tier required.

    Raises:
        FeatureGateError: If user's subscription tier is insufficient.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract subscription from kwargs (injected by FastAPI)
            subscription: Optional[Subscription] = kwargs.get("subscription")

            if not subscription:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Subscription dependency not found. "
                    "Add 'subscription: Subscription = Depends(get_current_subscription)' "
                    "to endpoint parameters.",
                )

            # Check tier hierarchy: TEAM > INDIVIDUAL
            tier_hierarchy = {
                SubscriptionTier.INDIVIDUAL: 1,
                SubscriptionTier.TEAM: 2,
            }

            user_tier_level = tier_hierarchy.get(subscription.tier, 0)
            required_tier_level = tier_hierarchy.get(tier, 999)

            if user_tier_level < required_tier_level:
                raise FeatureGateError(
                    feature=func.__name__, required_tier=tier
                )

            # User has sufficient tier, proceed
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_feature(feature: str, tier: SubscriptionTier):
    """
    Decorator: Require specific feature (alias for require_subscription).

    Usage:
        @router.post("/oauth/providers")
        @require_feature(feature="oauth", tier=SubscriptionTier.TEAM)
        async def add_oauth_provider(...):
            ...

    Args:
        feature: Feature name (for error messages).
        tier: Subscription tier that includes this feature.

    Raises:
        FeatureGateError: If user's subscription doesn't include feature.
    """
    return require_subscription(tier=tier)


async def check_user_limit(
    request: Request,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
    subscription: Subscription = Depends(get_current_subscription),
) -> bool:
    """
    Dependency: Check if user can add more team members.

    Returns:
        True if within user limit.

    Raises:
        HTTPException: If user limit would be exceeded.
    """
    from app.services.subscription_service import UserLimitExceededError

    # Get organization from membership
    if not user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "no_organization",
                "message": "User has no organization",
            },
        )

    # Resolve organization from JWT context (supports multi-org users)
    membership, organization_id = _resolve_organization(request, user, None)

    try:
        # Check if adding 1 more user is allowed
        await SubscriptionService.validate_user_limit(
            db, organization_id, additional_users=1
        )
        return True
    except UserLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "user_limit_exceeded",
                "message": str(e),
                "upgrade_url": "/billing/upgrade",
            },
        )
