"""
Enterprise Edition endpoints - License purchase and management.

Provides:
- POST /enterprise/checkout - Create Enterprise checkout (with Public Sector discount)
- GET /enterprise/eligibility - Check if user qualifies for Public Sector program
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...core.config import settings
from ...services.public_sector_service import PublicSectorService, is_public_sector_email
from ..dependencies import get_current_user_jwt, require_saas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])

# LemonSqueezy API base URL
LEMONSQUEEZY_API_URL = "https://api.lemonsqueezy.com/v1"


# ============================================================================
# Pydantic Models
# ============================================================================

class EnterpriseCheckoutRequest(BaseModel):
    """Request to create an Enterprise checkout session."""
    organization_name: str


class EnterpriseCheckoutResponse(BaseModel):
    """Response with checkout URL."""
    checkout_url: str
    is_public_sector: bool


class EligibilityResponse(BaseModel):
    """Response for Public Sector eligibility check."""
    is_eligible: bool
    domain: Optional[str] = None
    organization_name: Optional[str] = None
    category: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

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


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/eligibility", response_model=EligibilityResponse)
async def check_public_sector_eligibility(
    _: None = Depends(require_saas()),
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Check if the current user is eligible for the Public Sector Program.

    Government, education, and healthcare organizations receive
    free Enterprise licenses through automatic domain verification.

    Returns:
        EligibilityResponse with eligibility status and domain info
    """
    service = PublicSectorService(db)
    whitelist_entry = await service.get_domain_info(user.email)

    if whitelist_entry:
        return EligibilityResponse(
            is_eligible=True,
            domain=whitelist_entry.domain,
            organization_name=whitelist_entry.organization_name,
            category=whitelist_entry.category.value
        )

    return EligibilityResponse(is_eligible=False)


@router.post("/checkout", response_model=EnterpriseCheckoutResponse)
async def create_enterprise_checkout(
    data: EnterpriseCheckoutRequest,
    _: None = Depends(require_saas()),
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create an Enterprise license checkout session.

    For Public Sector organizations (verified government, education, healthcare),
    a 100% discount coupon is automatically applied server-side.

    SECURITY:
    - Coupon code is NEVER exposed to clients
    - Applied server-side only via LemonSqueezy API
    - Cannot be manually entered at checkout

    Returns:
        EnterpriseCheckoutResponse with checkout URL
    """
    # Check Enterprise variant is configured
    enterprise_variant_id = settings.lemonsqueezy_enterprise_variant_id
    if not enterprise_variant_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enterprise product not configured"
        )

    # Check Public Sector eligibility
    is_public = await is_public_sector_email(db, user.email)

    # Build checkout data
    checkout_data = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user.email,
                    "name": user.name or "",
                    "custom": {
                        "organization_name": data.organization_name,
                        "user_id": str(user.id),
                        "is_public_sector": "true" if is_public else "false",
                    }
                },
                "product_options": {
                    "redirect_url": f"{settings.domain}/app/subscription?enterprise_success=true",
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
                        "id": enterprise_variant_id
                    }
                }
            }
        }
    }

    # SERVER-SIDE ONLY: Apply 100% coupon for whitelisted public sector domains
    # This code is never disclosed to clients - coupon cannot be manually used
    if is_public:
        coupon_code = settings.PUBLIC_SECTOR_COUPON_CODE
        if coupon_code:
            checkout_data["data"]["attributes"]["discount_code"] = coupon_code
            logger.info(
                f"Public sector checkout: {user.email} "
                f"(org: {data.organization_name}) - coupon applied"
            )
        else:
            logger.warning(
                f"Public sector user {user.email} but PUBLIC_SECTOR_COUPON_CODE not configured"
            )
    else:
        logger.info(
            f"Enterprise checkout: {user.email} "
            f"(org: {data.organization_name}) - standard pricing"
        )

    # Create checkout via LemonSqueezy API
    headers = await get_lemonsqueezy_headers()

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

    return EnterpriseCheckoutResponse(
        checkout_url=checkout_url,
        is_public_sector=is_public
        # NOTE: We do NOT return the coupon code to the client
    )
