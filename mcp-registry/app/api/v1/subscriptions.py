"""
Subscription endpoints - LemonSqueezy integration for billing.

Provides:
- GET /subscriptions/status - Current subscription status
- POST /subscriptions/checkout - Create checkout link
- GET /subscriptions/portal - Get customer portal link
"""

import logging
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
from ...models.organization import Organization, OrganizationMember
from ...core.config import settings
from ..dependencies import get_current_user_jwt, get_current_organization_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

# LemonSqueezy API base URL
LEMONSQUEEZY_API_URL = "https://api.lemonsqueezy.com/v1"


# ============================================================================
# Pydantic Models
# ============================================================================

class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""
    plan: str  # "individual" or "team"
    organization_id: Optional[UUID] = None


class CheckoutResponse(BaseModel):
    """Response with checkout URL."""
    checkout_url: str
    plan: str


class PortalResponse(BaseModel):
    """Response with customer portal URL."""
    portal_url: str


class SubscriptionStatusResponse(BaseModel):
    """Current subscription status."""
    has_subscription: bool
    tier: Optional[str] = None
    status: Optional[str] = None
    is_active: bool = False
    is_trial: bool = False
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    max_users: int = 1
    features: dict = {}


class UsageResponse(BaseModel):
    """Usage metrics for current subscription."""
    connected_servers: int
    tool_executions: int
    compositions: int
    team_members: int
    max_team_members: int


# ============================================================================
# Helper Functions
# ============================================================================

def get_variant_id(plan: str) -> str:
    """Get LemonSqueezy variant ID for a plan."""
    if plan == "individual":
        variant_id = settings.lemonsqueezy_individual_variant_id
    elif plan == "team":
        variant_id = settings.lemonsqueezy_team_variant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {plan}. Must be 'individual' or 'team'"
        )

    if not variant_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Plan '{plan}' is not configured"
        )

    return variant_id


async def get_lemonsqueezy_headers() -> dict:
    """Get headers for LemonSqueezy API requests."""
    if not settings.lemonsqueezy_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LemonSqueezy billing is not configured"
        )

    return {
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }


async def get_user_organization(
    user: User,
    organization_id: Optional[UUID],
    db: AsyncSession,
    default_org_id: Optional[UUID] = None
) -> Optional[Organization]:
    """Get organization for the user."""
    if organization_id:
        # Verify user is member
        result = await db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user.id)
            .where(OrganizationMember.organization_id == organization_id)
        )
        membership = result.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization"
            )

        result = await db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        return result.scalar_one_or_none()

    # Use the resolved organization context
    if default_org_id:
        result = await db.execute(
            select(Organization).where(Organization.id == default_org_id)
        )
        return result.scalar_one_or_none()

    return None


async def get_user_subscription(
    org_id: UUID,
    db: AsyncSession
) -> Optional[Subscription]:
    """Get subscription for user's organization."""
    result = await db.execute(
        select(Subscription).where(Subscription.organization_id == org_id)
    )
    return result.scalar_one_or_none()


async def get_organization_subscription(
    db: AsyncSession,
    organization_id: UUID
) -> Optional[Subscription]:
    """
    Get subscription for a specific organization.

    Args:
        db: Database session
        organization_id: Organization ID

    Returns:
        Subscription if found, None otherwise
    """
    result = await db.execute(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def update_subscription_quantity(
    subscription_id: str,
    new_quantity: int,
    invoice_immediately: bool = True
) -> bool:
    """
    Update LemonSqueezy subscription quantity (seat count).

    This is called when team members are added or removed to sync billing.

    Args:
        subscription_id: LemonSqueezy subscription ID (e.g., "123456")
        new_quantity: New seat count
        invoice_immediately: If True, charge prorata immediately. If False, credit at next cycle.

    Returns:
        True if successful, False otherwise

    Example:
        # Member accepts invitation → increment seats
        success = await update_subscription_quantity(
            subscription.lemonsqueezy_subscription_id,
            current_members + 1,
            invoice_immediately=True
        )

        # Member removed → decrement seats
        success = await update_subscription_quantity(
            subscription.lemonsqueezy_subscription_id,
            remaining_members,
            invoice_immediately=False  # Credit at next billing cycle
        )
    """
    try:
        headers = await get_lemonsqueezy_headers()

        # LemonSqueezy PATCH /v1/subscriptions/{id}
        # See: https://docs.lemonsqueezy.com/api/subscriptions#update-a-subscription
        payload = {
            "data": {
                "type": "subscriptions",
                "id": subscription_id,
                "attributes": {
                    "invoice_immediately": invoice_immediately,
                    "product_options": {
                        "first_subscription_item": {
                            "quantity": new_quantity
                        }
                    }
                }
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{LEMONSQUEEZY_API_URL}/subscriptions/{subscription_id}",
                headers=headers,
                json=payload,
                timeout=30.0
            )

            if response.status_code not in [200, 204]:
                logger.error(
                    f"LemonSqueezy quantity update failed: "
                    f"{response.status_code} - {response.text}"
                )
                return False

            logger.info(
                f"✅ Updated subscription {subscription_id} quantity to {new_quantity} "
                f"(invoice_immediately={invoice_immediately})"
            )
            return True

    except Exception as e:
        logger.error(f"Exception updating LemonSqueezy subscription quantity: {e}")
        return False


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get current subscription status for the user.

    Returns subscription details including tier, status, and features.
    """
    _, org_id = org_context
    subscription = await get_user_subscription(org_id, db)

    if not subscription:
        return SubscriptionStatusResponse(
            has_subscription=False,
            is_active=False,
            features={
                "unlimited_ai_features": False,
                "organizations": False,
                "team_credentials": False,
            }
        )

    return SubscriptionStatusResponse(
        has_subscription=True,
        tier=subscription.tier.value,
        status=subscription.status.value,
        is_active=subscription.is_active,
        is_trial=subscription.is_trial,
        current_period_end=subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        cancel_at_period_end=subscription.cancel_at_period_end,
        max_users=subscription.max_users,
        features=subscription.get_tier_limits()
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a LemonSqueezy checkout session.

    Redirects the user to LemonSqueezy to complete payment.
    After payment, LemonSqueezy will send a webhook to create the subscription.
    """
    # Get variant ID for the plan
    variant_id = get_variant_id(data.plan)

    _, org_id = org_context
    # Get or create organization for the user
    organization = await get_user_organization(user, data.organization_id, db, default_org_id=org_id)

    if not organization:
        # Create a personal organization for the user
        organization = Organization(
            name=f"{user.name or user.email}'s Organization",
            slug=f"org-{user.id.hex[:8]}",
            owner_id=user.id
        )
        db.add(organization)
        await db.flush()

        # Add user as owner
        membership = OrganizationMember(
            organization_id=organization.id,
            user_id=user.id,
            role="owner"
        )
        db.add(membership)
        await db.commit()
        await db.refresh(organization)

    # Check if already has active subscription - redirect to portal for plan changes
    existing_sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.organization_id == organization.id)
        .where(Subscription.status.in_([
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING
        ]))
    )
    existing_sub = existing_sub_result.scalar_one_or_none()

    if existing_sub and existing_sub.lemonsqueezy_subscription_id:
        # User already has subscription - get portal URL from subscription details
        headers = await get_lemonsqueezy_headers()

        async with httpx.AsyncClient() as client:
            # GET subscription to retrieve customer_portal URL
            response = await client.get(
                f"{LEMONSQUEEZY_API_URL}/subscriptions/{existing_sub.lemonsqueezy_subscription_id}",
                headers=headers,
                timeout=30.0
            )

            if response.status_code == 200:
                result = response.json()
                urls = result.get("data", {}).get("attributes", {}).get("urls", {})
                portal_url = urls.get("customer_portal")

                if portal_url:
                    logger.info(f"Redirecting user {user.id} to portal for plan change")
                    return CheckoutResponse(
                        checkout_url=portal_url,
                        plan=data.plan
                    )

            logger.error(f"Failed to get portal URL: {response.status_code} - {response.text}")

        # Fallback if portal URL not available
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to access billing portal. Please try again."
        )

    # Create checkout via LemonSqueezy API
    headers = await get_lemonsqueezy_headers()

    checkout_data = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user.email,
                    "name": user.name or "",
                    "custom": {
                        "organization_id": str(organization.id),
                        "user_id": str(user.id)
                    }
                },
                "product_options": {
                    "redirect_url": f"{settings.domain}/app/subscription?success=true",
                },
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": settings.lemonsqueezy_store_id
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": variant_id
                    }
                }
            }
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LEMONSQUEEZY_API_URL}/checkouts",
            headers=headers,
            json=checkout_data,
            timeout=30.0
        )

        if response.status_code != 201:
            logger.error(f"LemonSqueezy checkout error: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create checkout session"
            )

        result = response.json()
        checkout_url = result["data"]["attributes"]["url"]

    logger.info(f"Created checkout for user {user.id}, plan {data.plan}, org {organization.id}")

    return CheckoutResponse(
        checkout_url=checkout_url,
        plan=data.plan
    )


@router.get("/portal", response_model=PortalResponse)
async def get_customer_portal(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get LemonSqueezy customer portal URL.

    Allows users to manage their subscription, update payment method,
    view invoices, and cancel subscription.
    """
    _, org_id = org_context
    subscription = await get_user_subscription(org_id, db)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found. Subscribe first."
        )

    if not subscription.lemonsqueezy_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription record found in billing system"
        )

    # Get customer portal URL from subscription details
    headers = await get_lemonsqueezy_headers()

    async with httpx.AsyncClient() as client:
        # GET subscription to retrieve customer_portal URL
        response = await client.get(
            f"{LEMONSQUEEZY_API_URL}/subscriptions/{subscription.lemonsqueezy_subscription_id}",
            headers=headers,
            timeout=30.0
        )

        if response.status_code == 200:
            result = response.json()
            urls = result.get("data", {}).get("attributes", {}).get("urls", {})
            portal_url = urls.get("customer_portal")

            if portal_url:
                return PortalResponse(portal_url=portal_url)

        logger.error(f"LemonSqueezy portal error: {response.status_code} - {response.text}")
        # Fallback: direct link to LemonSqueezy billing
        return PortalResponse(
            portal_url="https://app.lemonsqueezy.com/my-orders"
        )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get usage metrics for the current subscription.

    Returns counts of connected servers, tool executions, etc.
    """
    _, org_id = org_context
    subscription = await get_user_subscription(org_id, db)

    # Count connected servers (user credentials)
    from ...models.user_credential import UserCredential
    servers_result = await db.execute(
        select(UserCredential).where(UserCredential.user_id == user.id)
    )
    connected_servers = len(servers_result.scalars().all())

    # Count compositions
    from ...models.composition import Composition
    compositions_result = await db.execute(
        select(Composition).where(Composition.created_by == user.id)
    )
    compositions = len(compositions_result.scalars().all())

    # Count team members
    team_members = 1  # At least the user
    if org_id:
        members_result = await db.execute(
            select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
        )
        team_members = len(members_result.scalars().all())

    max_members = subscription.max_users if subscription else 1

    return UsageResponse(
        connected_servers=connected_servers,
        tool_executions=0,  # TODO: Track tool executions
        compositions=compositions,
        team_members=team_members,
        max_team_members=max_members
    )


@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Cancel current subscription.

    Subscription remains active until the end of the billing period.
    """
    _, org_id = org_context
    subscription = await get_user_subscription(org_id, db)

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found"
        )

    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already cancelled"
        )

    # Cancel via LemonSqueezy API
    headers = await get_lemonsqueezy_headers()

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{LEMONSQUEEZY_API_URL}/subscriptions/{subscription.lemonsqueezy_subscription_id}",
            headers=headers,
            timeout=30.0
        )

        if response.status_code not in [200, 204]:
            logger.error(f"LemonSqueezy cancel error: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to cancel subscription"
            )

    # Update local record
    subscription.cancel_at_period_end = True
    await db.commit()

    logger.info(f"Cancelled subscription {subscription.id} for user {user.id}")

    return {
        "message": "Subscription cancelled",
        "active_until": subscription.current_period_end.isoformat()
    }
