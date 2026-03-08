"""
LemonSqueezy webhook handlers for subscription and order lifecycle management.

Handles:
- Subscription events: created, updated, cancelled, expired (SaaS)
- Order events: created (Enterprise one-time purchases)
"""

import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, HTTPException, status, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...db.database import get_async_session
from ...models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from ...models.organization import Organization
from ...core.config import settings
from ...services.license_generator_service import (
    LicenseGeneratorService,
    LicenseAlreadyExistsError,
    NotSaaSEditionError,
    PrivateKeyNotConfiguredError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def verify_lemonsqueezy_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify LemonSqueezy webhook signature.

    LemonSqueezy uses HMAC SHA256 signature in X-Signature header.

    Args:
        payload: Raw request body bytes
        signature: Signature from X-Signature header
        secret: Webhook signing secret from LemonSqueezy settings

    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        logger.warning("LemonSqueezy webhook secret not configured, skipping signature verification")
        return True  # Allow in dev/test without secret

    # Compute HMAC SHA256
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(signature, expected_signature)


async def handle_subscription_created(
    event_data: Dict[str, Any],
    db: AsyncSession
) -> None:
    """
    Handle subscription.created event.

    Creates new Subscription record in database.
    Idempotent: skips if subscription already exists.
    """
    attributes = event_data["data"]["attributes"]

    # Extract LemonSqueezy data
    ls_subscription_id = str(event_data["data"]["id"])
    ls_customer_id = str(attributes.get("customer_id"))
    ls_variant_id = str(attributes.get("variant_id"))

    # Idempotency check: skip if subscription already exists
    existing = await db.execute(
        select(Subscription).where(
            Subscription.lemonsqueezy_subscription_id == ls_subscription_id
        )
    )
    if existing.scalar_one_or_none():
        logger.info(f"Subscription {ls_subscription_id} already exists, skipping creation")
        return

    status_str = attributes.get("status", "active")

    # Map LemonSqueezy status to our SubscriptionStatus
    status_mapping = {
        "on_trial": SubscriptionStatus.TRIALING,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "cancelled": SubscriptionStatus.CANCELLED,
        "expired": SubscriptionStatus.EXPIRED,
        "paused": SubscriptionStatus.CANCELLED,
    }
    subscription_status = status_mapping.get(status_str, SubscriptionStatus.ACTIVE)

    # Determine tier from variant_id (configured in settings)
    if ls_variant_id == settings.lemonsqueezy_team_variant_id:
        tier = SubscriptionTier.TEAM
        max_users = 0  # Team: unlimited users (0 = no limit)
    else:
        # Default to Individual for individual variant or unknown
        tier = SubscriptionTier.INDIVIDUAL
        max_users = 1

    # Get billing period dates
    # created_at = subscription creation time (period start)
    # renews_at = next renewal date (period end)
    current_period_start = datetime.fromisoformat(
        attributes["created_at"].replace("Z", "+00:00")
    ) if attributes.get("created_at") else datetime.now()

    current_period_end = datetime.fromisoformat(
        attributes["renews_at"].replace("Z", "+00:00")
    ) if attributes.get("renews_at") else datetime.now()

    cancel_at_period_end = attributes.get("cancelled", False)

    # Get organization from custom data (passed during checkout)
    # LemonSqueezy returns custom data in meta.custom_data, not attributes.custom_data
    meta = event_data.get("meta", {})
    custom_data = meta.get("custom_data", {})
    organization_id = custom_data.get("organization_id")

    # Log the custom_data for debugging
    logger.info(f"Webhook custom_data: {custom_data}")

    if not organization_id:
        logger.warning(
            f"No organization_id in custom_data for subscription {ls_subscription_id}"
        )
        return

    # Check if organization already has a subscription (upgrade scenario)
    existing_org_sub = await db.execute(
        select(Subscription).where(
            Subscription.organization_id == organization_id
        )
    )
    org_subscription = existing_org_sub.scalar_one_or_none()

    if org_subscription:
        # Upgrade: update existing subscription instead of creating a new one
        org_subscription.tier = tier
        org_subscription.status = subscription_status
        org_subscription.max_users = max_users
        org_subscription.lemonsqueezy_subscription_id = ls_subscription_id
        org_subscription.lemonsqueezy_customer_id = ls_customer_id
        org_subscription.lemonsqueezy_variant_id = ls_variant_id
        org_subscription.current_period_start = current_period_start
        org_subscription.current_period_end = current_period_end
        org_subscription.cancel_at_period_end = cancel_at_period_end

        await db.commit()

        logger.info(
            f"✅ Upgraded subscription {org_subscription.id} for org {organization_id} "
            f"(LemonSqueezy: {ls_subscription_id}, tier: {tier.value})"
        )
        return

    # Create new subscription
    subscription = Subscription(
        tier=tier,
        status=subscription_status,
        organization_id=organization_id,
        max_users=max_users,
        lemonsqueezy_subscription_id=ls_subscription_id,
        lemonsqueezy_customer_id=ls_customer_id,
        lemonsqueezy_variant_id=ls_variant_id,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )

    db.add(subscription)
    await db.commit()

    logger.info(
        f"✅ Created subscription {subscription.id} for org {organization_id} "
        f"(LemonSqueezy: {ls_subscription_id}, tier: {tier.value})"
    )


async def handle_subscription_updated(
    event_data: Dict[str, Any],
    db: AsyncSession
) -> None:
    """
    Handle subscription.updated event.

    Updates existing Subscription record.
    """
    attributes = event_data["data"]["attributes"]
    ls_subscription_id = str(event_data["data"]["id"])

    # Find subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.lemonsqueezy_subscription_id == ls_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"Subscription not found for LemonSqueezy ID: {ls_subscription_id}")
        return

    # Update status
    status_str = attributes.get("status", "active")
    status_mapping = {
        "on_trial": SubscriptionStatus.TRIALING,
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "cancelled": SubscriptionStatus.CANCELLED,
        "expired": SubscriptionStatus.EXPIRED,
        "paused": SubscriptionStatus.CANCELLED,
    }
    subscription.status = status_mapping.get(status_str, SubscriptionStatus.ACTIVE)

    # Update billing period
    if attributes.get("renews_at"):
        subscription.current_period_end = datetime.fromisoformat(
            attributes["renews_at"].replace("Z", "+00:00")
        )

    # Update cancellation status
    subscription.cancel_at_period_end = attributes.get("cancelled", False)

    # Update user count (if changed)
    user_count = attributes.get("first_subscription_item", {}).get("quantity", 1)
    if subscription.tier == SubscriptionTier.TEAM and user_count != subscription.max_users:
        subscription.max_users = user_count

    await db.commit()

    logger.info(
        f"✅ Updated subscription {subscription.id} "
        f"(status: {subscription.status.value}, cancel_at_period_end: {subscription.cancel_at_period_end})"
    )


async def handle_subscription_cancelled(
    event_data: Dict[str, Any],
    db: AsyncSession
) -> None:
    """
    Handle subscription_cancelled event.

    Marks subscription as cancelled.
    """
    ls_subscription_id = str(event_data["data"]["id"])

    # Find subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.lemonsqueezy_subscription_id == ls_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"Subscription not found for LemonSqueezy ID: {ls_subscription_id}")
        return

    # Mark as cancelled (but keep active until period end)
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancel_at_period_end = True

    await db.commit()

    logger.info(
        f"✅ Cancelled subscription {subscription.id} "
        f"(access until {subscription.current_period_end})"
    )


async def handle_subscription_expired(
    event_data: Dict[str, Any],
    db: AsyncSession
) -> None:
    """
    Handle subscription_expired event.

    Marks subscription as expired (no access).
    """
    ls_subscription_id = str(event_data["data"]["id"])

    # Find subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.lemonsqueezy_subscription_id == ls_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"Subscription not found for LemonSqueezy ID: {ls_subscription_id}")
        return

    # Mark as expired
    subscription.status = SubscriptionStatus.EXPIRED

    await db.commit()

    logger.info(f"✅ Expired subscription {subscription.id}")


async def handle_order_created(
    event_data: Dict[str, Any],
    db: AsyncSession
) -> None:
    """
    Handle order_created event for Enterprise one-time purchases.

    Generates an Enterprise LICENSE_KEY JWT and stores it in the database.
    The license is linked by customer email for retrieval via dashboard.

    Idempotent: skips if license for order already exists.
    Only operates on SaaS edition with LICENSE_SIGNING_PRIVATE_KEY configured.
    """
    attributes = event_data["data"]["attributes"]

    # Extract order data
    order_id = str(event_data["data"]["id"])
    status_str = attributes.get("status", "pending")

    # Only process paid orders
    if status_str != "paid":
        logger.info(f"Order {order_id} status is '{status_str}', skipping license generation")
        return

    # Extract customer info
    customer_id = str(attributes.get("customer_id", ""))
    customer_email = attributes.get("user_email", "")
    customer_name = attributes.get("user_name", "")

    # Check if this is an Enterprise product order
    # LemonSqueezy orders have first_order_item with variant_id
    first_item = attributes.get("first_order_item", {})
    variant_id = str(first_item.get("variant_id", ""))

    # Verify this is an Enterprise variant (configured in settings)
    enterprise_variant_id = getattr(settings, 'lemonsqueezy_enterprise_variant_id', None)
    if enterprise_variant_id and variant_id != enterprise_variant_id:
        logger.info(
            f"Order {order_id} variant {variant_id} is not Enterprise "
            f"(expected {enterprise_variant_id}), skipping"
        )
        return

    if not customer_email:
        logger.error(f"Order {order_id} missing customer email, cannot generate license")
        return

    # Get organization name from custom data or customer name
    meta = event_data.get("meta", {})
    custom_data = meta.get("custom_data", {})
    org_name = custom_data.get("organization_name") or customer_name or customer_email

    # Determine license duration based on order total
    # Total is in cents (e.g. 9900 = €99.00, 0 = free/promo)
    order_total = attributes.get("total", 0)  # in cents
    if order_total == 0:
        # Free/promo order → 3-month timed license
        license_expires_at = datetime.now() + timedelta(days=90)
        logger.info(f"Order {order_id} is free (total=0) → 3-month license until {license_expires_at.date()}")
    else:
        # Paid order → perpetual license
        license_expires_at = None
        logger.info(f"Order {order_id} is paid (total={order_total}) → perpetual license")

    logger.info(
        f"Processing Enterprise order {order_id} for {customer_email} ({org_name})"
    )

    try:
        # Generate and store license
        license_record = await LicenseGeneratorService.generate_and_store_license(
            session=db,
            org_name=org_name,
            order_id=order_id,
            customer_email=customer_email,
            customer_id=customer_id,
            expires_at=license_expires_at,
        )

        logger.info(
            f"✅ Created Enterprise license {license_record.id} for order {order_id} "
            f"(email: {customer_email})"
        )

    except LicenseAlreadyExistsError:
        logger.info(f"License for order {order_id} already exists, skipping")
        return

    except NotSaaSEditionError:
        logger.error(
            f"Cannot generate license for order {order_id}: "
            "Not running on SaaS edition"
        )
        return

    except PrivateKeyNotConfiguredError:
        logger.error(
            f"Cannot generate license for order {order_id}: "
            "LICENSE_SIGNING_PRIVATE_KEY not configured"
        )
        return


# Event handler mapping
EVENT_HANDLERS = {
    # Subscription events (SaaS recurring billing)
    "subscription_created": handle_subscription_created,
    "subscription_updated": handle_subscription_updated,
    "subscription_cancelled": handle_subscription_cancelled,
    "subscription_expired": handle_subscription_expired,
    "subscription_payment_failed": handle_subscription_updated,  # Update status to past_due
    "subscription_payment_success": handle_subscription_updated,  # Update status to active
    # Order events (Enterprise one-time purchases)
    "order_created": handle_order_created,
}


@router.post("/lemonsqueezy")
async def lemonsqueezy_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_async_session)
):
    """
    LemonSqueezy webhook endpoint.

    Handles all subscription lifecycle events from LemonSqueezy.

    Events:
    - subscription_created: New subscription created
    - subscription_updated: Subscription details changed
    - subscription_cancelled: User cancelled subscription
    - subscription_expired: Subscription expired (no payment)
    - subscription_payment_failed: Payment failed (grace period)
    - subscription_payment_success: Payment succeeded

    Security:
    - Verifies HMAC SHA256 signature from X-Signature header
    - Returns 401 if signature is invalid

    Idempotency:
    - Safe to receive duplicate events
    - Updates are idempotent
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature - REQUIRED when webhook secret is configured
    webhook_secret = settings.lemonsqueezy_webhook_secret

    if webhook_secret:
        if not x_signature:
            logger.error("❌ Missing X-Signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature"
            )
        if not verify_lemonsqueezy_signature(body, x_signature, webhook_secret):
            logger.error("❌ Invalid LemonSqueezy webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
    else:
        logger.warning("⚠️ Webhook secret not configured - signature verification skipped")

    # Parse JSON
    event_data = await request.json()

    # Get event type
    event_name = event_data.get("meta", {}).get("event_name")

    if not event_name:
        logger.warning("No event_name in webhook payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event_name"
        )

    logger.info(f"📬 Received LemonSqueezy webhook: {event_name}")

    # Handle event
    handler = EVENT_HANDLERS.get(event_name)

    if handler:
        try:
            await handler(event_data, db)
        except Exception as e:
            logger.exception(f"❌ Error handling {event_name}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing event: {str(e)}"
            )
    else:
        logger.info(f"ℹ️  Unhandled event type: {event_name}")

    return {"status": "success", "event": event_name}
