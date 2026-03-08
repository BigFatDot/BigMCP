"""
Marketplace API Key management endpoints.

Allows users to create, list, and revoke marketplace API keys for self-hosted deployments.
"""

from typing import List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ...db.database import get_async_session
from ...models.user import User
from ...models.marketplace_api_key import MarketplaceAPIKey, DeploymentType
from ...api.dependencies import get_current_user_jwt


router = APIRouter(prefix="/marketplace-keys", tags=["Marketplace Keys"])


# ===== Request/Response Models =====

class MarketplaceAPIKeyCreate(BaseModel):
    """Request model for creating marketplace API key."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-friendly name (e.g., 'Production Server', 'Dev Environment')"
    )
    deployment_type: DeploymentType = Field(
        default=DeploymentType.SELF_HOSTED_COMMUNITY,
        description="Deployment type for usage tracking"
    )


class MarketplaceAPIKeyResponse(BaseModel):
    """Response model for marketplace API key (without actual key)."""
    id: UUID
    name: str
    key_prefix: str
    deployment_type: DeploymentType
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    request_count: int
    rate_limit_per_minute: int

    class Config:
        from_attributes = True


class MarketplaceAPIKeyCreateResponse(BaseModel):
    """Response model for newly created API key (includes actual key once)."""
    id: UUID
    name: str
    key: str  # ⚠️ Only returned once on creation!
    key_prefix: str
    deployment_type: DeploymentType
    created_at: datetime
    rate_limit_per_minute: int

    warning: str = (
        "⚠️ IMPORTANT: Save this API key now. "
        "It will not be shown again for security reasons."
    )


# ===== Endpoints =====

@router.post("/", response_model=MarketplaceAPIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_marketplace_api_key(
    data: MarketplaceAPIKeyCreate,
    current_user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new marketplace API key.

    **IMPORTANT:** The API key is only returned once. Save it securely.

    Cloud users can create API keys for testing, but JWT is recommended.
    Self-hosted users need API keys to access the marketplace.

    **Rate Limiting:** All API keys have a default limit of 100 requests/minute.

    **Example:**
    ```json
    {
        "name": "Production Server",
        "deployment_type": "self_hosted_community"
    }
    ```

    **Returns:**
    - API key (only shown once!)
    - Key prefix for identification
    - Rate limiting info
    """
    # Generate API key
    raw_key = MarketplaceAPIKey.generate_api_key()
    key_hash = MarketplaceAPIKey.hash_key(raw_key)
    key_prefix = MarketplaceAPIKey.get_key_prefix(raw_key)

    # Create API key record
    api_key = MarketplaceAPIKey(
        user_id=current_user.id,
        key_name=data.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        deployment_type=data.deployment_type,
        is_active=True,
        rate_limit_per_minute=100  # Free tier default
    )

    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    # Return response with actual key (only time it's shown!)
    return MarketplaceAPIKeyCreateResponse(
        id=api_key.id,
        name=api_key.key_name,
        key=raw_key,  # ⚠️ Only returned here!
        key_prefix=api_key.key_prefix,
        deployment_type=api_key.deployment_type,
        created_at=api_key.created_at,
        rate_limit_per_minute=api_key.rate_limit_per_minute
    )


@router.get("/", response_model=List[MarketplaceAPIKeyResponse])
async def list_marketplace_api_keys(
    current_user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
    include_revoked: bool = False
):
    """
    List all marketplace API keys for current user.

    **Parameters:**
    - `include_revoked`: Include revoked keys in results (default: False)

    **Returns:**
    - List of API keys with usage stats
    - Keys are ordered by creation date (newest first)
    """
    # Build query
    query = select(MarketplaceAPIKey).where(
        MarketplaceAPIKey.user_id == current_user.id
    )

    # Filter by active status if requested
    if not include_revoked:
        query = query.where(MarketplaceAPIKey.is_active == True)

    # Order by creation date (newest first)
    query = query.order_by(desc(MarketplaceAPIKey.created_at))

    # Execute query
    result = await db.execute(query)
    api_keys = result.scalars().all()

    return [
        MarketplaceAPIKeyResponse(
            id=key.id,
            name=key.key_name,
            key_prefix=key.key_prefix,
            deployment_type=key.deployment_type,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            request_count=key.request_count,
            rate_limit_per_minute=key.rate_limit_per_minute
        )
        for key in api_keys
    ]


@router.get("/{key_id}", response_model=MarketplaceAPIKeyResponse)
async def get_marketplace_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get details of a specific marketplace API key.

    **Returns:**
    - API key details with usage stats
    - Does NOT include the actual key (security)
    """
    # Query for API key
    result = await db.execute(
        select(MarketplaceAPIKey).where(
            MarketplaceAPIKey.id == key_id,
            MarketplaceAPIKey.user_id == current_user.id
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace API key not found"
        )

    return MarketplaceAPIKeyResponse(
        id=api_key.id,
        name=api_key.key_name,
        key_prefix=api_key.key_prefix,
        deployment_type=api_key.deployment_type,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        request_count=api_key.request_count,
        rate_limit_per_minute=api_key.rate_limit_per_minute
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_marketplace_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Revoke a marketplace API key.

    **IMPORTANT:** This action is irreversible. The key will be deactivated immediately.

    Revoked keys:
    - Cannot be reactivated
    - Will fail authentication
    - Remain in the database for audit purposes
    """
    # Query for API key
    result = await db.execute(
        select(MarketplaceAPIKey).where(
            MarketplaceAPIKey.id == key_id,
            MarketplaceAPIKey.user_id == current_user.id
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketplace API key not found"
        )

    # Check if already revoked
    if api_key.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is already revoked"
        )

    # Revoke the key
    api_key.revoke()
    await db.commit()

    return None  # 204 No Content
