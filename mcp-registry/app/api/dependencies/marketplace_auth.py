"""
Marketplace authentication dependencies.

Supports dual authentication:
- Cloud users: JWT tokens (primary authentication)
- Self-hosted users: Marketplace API keys (created after registration)
"""

from typing import Optional
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...db.database import get_async_session
from ...models.user import User
from ...models.marketplace_api_key import MarketplaceAPIKey, DeploymentType
from ...services.auth_service import AuthService
from ..dependencies import get_auth_service


# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class MarketplaceUser:
    """
    Authenticated marketplace user.

    Represents either a Cloud user (JWT auth) or Self-hosted user (API key auth).
    """
    user_id: UUID
    user_email: str
    deployment_type: DeploymentType
    auth_method: str  # "jwt" or "api_key"
    api_key_id: Optional[UUID] = None  # Present for API key auth
    rate_limit_per_minute: int = 100  # Free tier default


async def get_marketplace_api_key(
    key: str,
    db: AsyncSession
) -> Optional[tuple[MarketplaceAPIKey, User]]:
    """
    Validate marketplace API key and return key + user.

    Args:
        key: Raw API key string (mcphub_mk_...)
        db: Database session

    Returns:
        tuple: (MarketplaceAPIKey, User) or None if invalid
    """
    # Hash the key for lookup
    key_hash = MarketplaceAPIKey.hash_key(key)

    # Query for API key with user relationship
    result = await db.execute(
        select(MarketplaceAPIKey)
        .where(
            MarketplaceAPIKey.key_hash == key_hash,
            MarketplaceAPIKey.is_active == True
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    # Check if revoked
    if api_key.is_revoked:
        return None

    # Get user
    result = await db.execute(
        select(User).where(User.id == api_key.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return None

    # Record usage
    api_key.record_usage()
    await db.commit()

    return api_key, user


async def get_marketplace_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_async_session)
) -> MarketplaceUser:
    """
    Authenticate marketplace request from Cloud (JWT) or Self-hosted (API key).

    Authentication flow:
    1. Try JWT first (Cloud users)
    2. Try marketplace API key (Self-hosted users)
    3. Return 401 if both fail

    Usage:
        @router.get("/marketplace/servers")
        async def list_servers(
            marketplace_user: MarketplaceUser = Depends(get_marketplace_user)
        ):
            # Access marketplace_user.deployment_type, etc.
            pass

    Returns:
        MarketplaceUser: Authenticated user with deployment info

    Raises:
        HTTPException: 401 if authentication fails
    """
    # Extract token from Authorization header
    token = None
    if credentials:
        token = credentials.credentials
    elif authorization:
        # Handle "Bearer <token>" format
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() != "bearer":
                token = None
        except ValueError:
            token = None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_required",
                "message": "Marketplace access requires authentication",
                "supported_methods": ["jwt", "api_key"]
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try JWT authentication (Cloud users)
    if token.startswith("eyJ"):  # JWT tokens start with "eyJ"
        user = await auth_service.get_user_from_token(token)
        if user:
            return MarketplaceUser(
                user_id=user.id,
                user_email=user.email,
                deployment_type=DeploymentType.CLOUD,
                auth_method="jwt",
                rate_limit_per_minute=100
            )

    # Try marketplace API key authentication (Self-hosted users)
    if token.startswith("mcphub_mk_"):
        result = await get_marketplace_api_key(token, db)
        if result:
            api_key, user = result
            return MarketplaceUser(
                user_id=user.id,
                user_email=user.email,
                deployment_type=api_key.deployment_type,
                auth_method="api_key",
                api_key_id=api_key.id,
                rate_limit_per_minute=api_key.rate_limit_per_minute
            )

    # Authentication failed
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "invalid_credentials",
            "message": "Invalid or expired authentication token",
            "hint": "Cloud users: Use JWT token. Self-hosted users: Use marketplace API key (mcphub_mk_...)"
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_marketplace_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_async_session)
) -> Optional[MarketplaceUser]:
    """
    Authenticate marketplace user if credentials provided, otherwise return None.

    Useful for endpoints that support both authenticated and anonymous access.

    Usage:
        @router.get("/marketplace/servers")
        async def list_servers(
            marketplace_user: Optional[MarketplaceUser] = Depends(get_marketplace_user_optional)
        ):
            if marketplace_user:
                # Return user-specific results
            else:
                # Return public results
            pass

    Returns:
        MarketplaceUser or None
    """
    try:
        return await get_marketplace_user(credentials, authorization, auth_service, db)
    except HTTPException:
        return None
