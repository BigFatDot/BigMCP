"""
API Keys endpoints - CRUD operations for API keys.

Allows users to create, list, update, and revoke API keys.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ...services.auth_service import AuthService
from ...schemas.auth import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyUpdate
)
from ..dependencies import get_current_user_jwt, get_current_organization_jwt, get_auth_service


router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: APIKeyCreate,
    organization_id: Optional[UUID] = Query(None, description="Organization ID (defaults to user's first org)"),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new API key for the current user.

    The API key secret is returned ONLY ONCE. Save it securely!

    Args:
        data: API key creation data
        organization_id: Organization to create key for (optional)

    Returns:
        APIKeyCreateResponse: Created API key with secret
    """
    # Get organization ID
    if organization_id is None:
        _, organization_id = org_context
    else:
        # Verify user is member of organization
        membership = await auth_service.check_user_org_membership(user.id, organization_id)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization"
            )

    # Check for duplicate name in organization
    result = await db.execute(
        select(APIKey)
        .where(APIKey.organization_id == organization_id)
        .where(APIKey.name == data.name)
    )
    existing_key = result.scalar_one_or_none()

    if existing_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"API key with name '{data.name}' already exists in this organization"
        )

    # Create API key
    api_key, secret = await auth_service.create_api_key(
        user_id=user.id,
        organization_id=organization_id,
        name=data.name,
        scopes=data.scopes,
        tool_group_id=data.tool_group_id,
        description=data.description,
        expires_at=data.expires_at
    )

    return APIKeyCreateResponse(
        api_key=api_key,
        secret=secret
    )


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    organization_id: Optional[UUID] = Query(None, description="Organization ID (defaults to user's first org)"),
    include_revoked: bool = Query(False, description="Include revoked (inactive) keys"),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    List API keys for the current user in an organization.

    Args:
        organization_id: Organization to list keys for (optional)
        include_revoked: Include revoked keys in the list (default: False)

    Returns:
        list[APIKeyResponse]: List of API keys (without secrets)
    """
    # Get organization ID
    if organization_id is None:
        _, organization_id = org_context
    else:
        # Verify user is member of organization
        membership = await auth_service.check_user_org_membership(user.id, organization_id)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization"
            )

    # List API keys (by default excludes revoked keys)
    api_keys = await auth_service.list_user_api_keys(
        user.id,
        organization_id,
        include_revoked=include_revoked
    )
    return api_keys


@router.get("/{api_key_id}", response_model=APIKeyResponse)
async def get_api_key(
    api_key_id: UUID,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get details of a specific API key.

    Args:
        api_key_id: API key UUID

    Returns:
        APIKeyResponse: API key details (without secret)
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == api_key_id)
        .where(APIKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return api_key


@router.patch("/{api_key_id}", response_model=APIKeyResponse)
async def update_api_key(
    api_key_id: UUID,
    data: APIKeyUpdate,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update an API key.

    Can update: name, description, scopes, is_active
    Cannot update: secret (revoke and create new instead)

    Args:
        api_key_id: API key UUID
        data: Update data

    Returns:
        APIKeyResponse: Updated API key
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == api_key_id)
        .where(APIKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Update fields
    if data.name is not None:
        # Check for duplicate name
        result = await db.execute(
            select(APIKey)
            .where(APIKey.organization_id == api_key.organization_id)
            .where(APIKey.name == data.name)
            .where(APIKey.id != api_key_id)
        )
        existing_key = result.scalar_one_or_none()
        if existing_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API key with name '{data.name}' already exists"
            )
        api_key.name = data.name

    if data.description is not None:
        api_key.description = data.description

    if data.scopes is not None:
        api_key.scopes = data.scopes

    if data.is_active is not None:
        api_key.is_active = data.is_active

    await db.commit()
    await db.refresh(api_key)

    return api_key


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: UUID,
    user: User = Depends(get_current_user_jwt),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Revoke (deactivate) an API key.

    The key will no longer be valid for authentication.
    This action cannot be undone - create a new key instead.

    Args:
        api_key_id: API key UUID

    Returns:
        204 No Content on success
    """
    success = await auth_service.revoke_api_key(api_key_id, user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return None


@router.post("/{api_key_id}/activate", response_model=APIKeyResponse)
async def activate_api_key(
    api_key_id: UUID,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Reactivate a previously revoked API key.

    Args:
        api_key_id: API key UUID

    Returns:
        APIKeyResponse: Reactivated API key
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.id == api_key_id)
        .where(APIKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Check if expired
    if api_key.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reactivate expired API key"
        )

    api_key.is_active = True
    await db.commit()
    await db.refresh(api_key)

    return api_key
