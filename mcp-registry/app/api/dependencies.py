"""
FastAPI dependencies for authentication and authorization.

Provides reusable dependencies for route protection.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Header, Request, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_async_session
from ..models.user import User
from ..models.api_key import APIKey
from ..models.organization import UserRole, OrganizationMember
from ..services.auth_service import AuthService
from ..core.rls_context import set_organization_context_safe


# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)


# ===== Database Dependency =====

async def get_auth_service(db: AsyncSession = Depends(get_async_session)) -> AuthService:
    """Get AuthService instance with database session."""
    return AuthService(db)


# ===== JWT Authentication =====

async def get_current_user_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    access_token: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """
    Get current user from JWT Bearer token (header or cookie).

    Tries Authorization header first, then access_token cookie.

    Usage:
        @app.get("/me")
        async def get_me(user: User = Depends(get_current_user_jwt)):
            return user

    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    # Try to get token from Authorization header first
    token = None
    if credentials:
        token = credentials.credentials
    # Fall back to cookie if header not present
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_service.get_user_from_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ===== API Key Authentication =====

async def get_current_user_api_key(
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service)
) -> tuple[APIKey, User]:
    """
    Get current user and API key from API Key in Authorization header.

    Expects: Authorization: Bearer mcphub_sk_abc123...

    Usage:
        @app.get("/tools")
        async def list_tools(auth: tuple[APIKey, User] = Depends(get_current_user_api_key)):
            api_key, user = auth
            return {"user": user.email, "key": api_key.name}

    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract API key from "Bearer mcphub_sk_abc123..."
    try:
        scheme, key = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate API key
    result = await auth_service.validate_api_key(key)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key, user = result
    return api_key, user


# ===== Dual Authentication (JWT or API Key) =====

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    authorization: Optional[str] = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
    request: Request = None
) -> tuple[User, Optional[APIKey]]:
    """
    Get current user from either JWT or API Key.

    Tries JWT first, then API Key.
    Returns tuple of (User, APIKey) where APIKey is None for JWT auth.

    Usage:
        @app.get("/me")
        async def get_me(auth: tuple[User, Optional[APIKey]] = Depends(get_current_user)):
            user, api_key = auth
            if api_key:
                return {"user": user.email, "auth_method": "api_key", "key_name": api_key.name}
            else:
                return {"user": user.email, "auth_method": "jwt"}

    Raises:
        HTTPException: 401 if no valid authentication
    """
    # Try JWT first
    if credentials:
        token = credentials.credentials
        user = await auth_service.get_user_from_token(token)
        if user:
            return user, None

    # Try API Key
    if authorization:
        try:
            scheme, key = authorization.split(" ", 1)
            if scheme.lower() == "bearer":
                result = await auth_service.validate_api_key(key)
                if result:
                    api_key, user = result
                    return user, api_key
        except ValueError:
            pass

    # No valid authentication — build OAuth discovery URL for clients
    # Use X-Forwarded-Proto and Host headers (set by nginx) to get public URL
    if request:
        scheme = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("host", str(request.base_url.hostname))
        base_url = f"{scheme}://{host}"
    else:
        base_url = f"http://localhost"

    # MCP 2025-03-26 spec: WWW-Authenticate must include resource_metadata
    resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"
    www_authenticate = (
        f'Bearer '
        f'resource_metadata="{resource_metadata_url}"'
    )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "unauthorized",
            "error_description": "Authentication required",
            "oauth_discovery": f"{base_url}/.well-known/oauth-authorization-server",
            "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
            "token_endpoint": f"{base_url}/api/v1/oauth/token"
        },
        headers={
            "WWW-Authenticate": www_authenticate,
        },
    )


# ===== Scope Validation =====

def require_scope(scope: str):
    """
    Dependency factory to require a specific scope.

    Usage:
        @app.post("/tools/execute")
        async def execute_tool(
            auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
            _: None = Depends(require_scope("tools:execute"))
        ):
            # Only users/keys with "tools:execute" scope can access
            pass

    Args:
        scope: Required scope (e.g., "tools:execute")

    Raises:
        HTTPException: 403 if user doesn't have required scope
    """
    async def check_scope(auth: tuple[User, Optional[APIKey]] = Depends(get_current_user)):
        user, api_key = auth

        # If authenticated with API Key, check scopes
        if api_key:
            if not api_key.has_scope(scope):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required scope: {scope}"
                )
        # If authenticated with JWT, user has all scopes (for now)
        # TODO: Add role-based scopes to users

        return None

    return check_scope


# ===== Organization Context Resolution =====

def _extract_org_id_from_jwt(request: Request) -> Optional[str]:
    """
    Extract org_id from JWT Bearer token in request headers.

    Returns:
        org_id string or None if not present or invalid token.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "")

    # Avoid re-importing; AuthService.decode_token is a static method
    payload = AuthService.decode_token(token)
    if payload:
        return payload.get("org_id")
    return None


def _resolve_organization(
    request: Request,
    user: User,
    api_key: Optional[APIKey]
) -> tuple[OrganizationMember, UUID]:
    """
    Core logic for resolving the current organization context.

    Priority:
    1. API Key auth → use key's organization_id
    2. JWT with org_id claim → use token's organization
    3. Single membership → no ambiguity, use it
    4. Multiple memberships without context → error

    Args:
        request: FastAPI Request (to extract JWT)
        user: Authenticated user with organization_memberships loaded
        api_key: API key if auth was via API key, None otherwise

    Returns:
        tuple[OrganizationMember, UUID]: (membership, organization_id)

    Raises:
        HTTPException 400: No membership or ambiguous context
        HTTPException 403: API key org mismatch
    """
    if not user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no organization membership"
        )

    # 1. API Key: organization is fixed by the key
    if api_key:
        for m in user.organization_memberships:
            if m.organization_id == api_key.organization_id:
                return m, m.organization_id
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key organization mismatch - user is not a member"
        )

    # 2. JWT with org_id: use the token's organization context
    org_id_str = _extract_org_id_from_jwt(request)
    if org_id_str:
        for m in user.organization_memberships:
            if str(m.organization_id) == org_id_str:
                return m, m.organization_id
        # org_id in JWT but user no longer member: fall through to fallback

    # 3. Single membership: no ambiguity
    if len(user.organization_memberships) == 1:
        m = user.organization_memberships[0]
        return m, m.organization_id

    # 4. Multiple memberships without context: explicit error
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Organization context required for multi-org users. Use switch-organization endpoint."
    )


async def get_current_organization(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> tuple[OrganizationMember, UUID]:
    """
    Get current organization context and set RLS context.

    For endpoints that use get_current_user (dual JWT/API Key auth).
    This also sets the PostgreSQL RLS context for defense-in-depth.

    Usage:
        @router.get("/items")
        async def list_items(
            org_context: tuple[OrganizationMember, UUID] = Depends(get_current_organization),
        ):
            membership, organization_id = org_context
            ...

    Returns:
        tuple[OrganizationMember, UUID]: (membership, organization_id)
    """
    user, api_key = auth
    membership, org_id = _resolve_organization(request, user, api_key)

    # Set RLS context for defense-in-depth (no-op on SQLite)
    await set_organization_context_safe(db, org_id)

    return membership, org_id


async def get_current_organization_jwt(
    request: Request,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session),
) -> tuple[OrganizationMember, UUID]:
    """
    Get current organization context and set RLS context.

    For endpoints that use get_current_user_jwt (JWT-only auth).
    This also sets the PostgreSQL RLS context for defense-in-depth.

    Usage:
        @router.get("/compositions")
        async def list_compositions(
            org_context: tuple[OrganizationMember, UUID] = Depends(get_current_organization_jwt),
        ):
            membership, organization_id = org_context
            ...

    Returns:
        tuple[OrganizationMember, UUID]: (membership, organization_id)
    """
    membership, org_id = _resolve_organization(request, user, None)

    # Set RLS context for defense-in-depth (no-op on SQLite)
    await set_organization_context_safe(db, org_id)

    return membership, org_id


# ===== Organization Membership (legacy, kept for compatibility) =====

async def get_user_organization(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    organization_id: Optional[UUID] = None
) -> UUID:
    """
    Get and validate user's organization, and set RLS context.

    If organization_id is provided, validates user membership.
    If not provided, resolves from JWT context or single membership.
    Also sets the PostgreSQL RLS context for defense-in-depth.

    Returns:
        UUID: Validated organization ID
    """
    user, api_key = auth
    resolved_org_id = None

    # If API key is used, get organization from API key
    if api_key:
        if organization_id and api_key.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key not authorized for this organization"
            )
        resolved_org_id = api_key.organization_id
    # If explicit organization_id provided, validate membership
    elif organization_id:
        is_member = any(
            m.organization_id == organization_id
            for m in user.organization_memberships
        )
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of this organization"
            )
        resolved_org_id = organization_id
    else:
        # Resolve from context
        _, resolved_org_id = _resolve_organization(request, user, api_key)

    # Set RLS context for defense-in-depth (no-op on SQLite)
    await set_organization_context_safe(db, resolved_org_id)

    return resolved_org_id


# ===== Admin Check =====

async def require_admin(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    organization_id: UUID = Depends(get_user_organization),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """
    Require user to be admin of organization.

    Usage:
        @app.post("/organizations/{organization_id}/credentials")
        async def create_org_credential(
            organization_id: UUID,
            admin_user: User = Depends(require_admin)
        ):
            # Only admins can access
            pass

    Raises:
        HTTPException: 403 if user is not admin
    """
    user, api_key = auth

    # Check if user is admin
    is_admin = await auth_service.check_user_admin(user.id, organization_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return user


async def get_current_admin_user(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """
    Get current user and verify they have ADMIN or OWNER role
    in the current organization context.

    Usage:
        @app.post("/org-credentials/")
        async def create_org_credential(
            current_user: User = Depends(get_current_admin_user)
        ):
            # Only admins can access
            pass

    Raises:
        HTTPException: 403 if user has no organization or insufficient role
    """
    user, api_key = auth

    # Resolve organization using centralized logic
    membership, organization_id = _resolve_organization(request, user, api_key)

    # Check if user has admin role in the resolved organization
    if membership.role not in [UserRole.ADMIN, UserRole.OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role required"
        )

    return user


# ===== Optional Authentication =====

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[tuple[User, Optional[APIKey]]]:
    """
    Get current user if authenticated, None otherwise.

    Supports JWT (header/cookie) and API Key authentication.

    Usage:
        @app.get("/tools")
        async def list_tools(
            auth: Optional[tuple[User, Optional[APIKey]]] = Depends(get_current_user_optional)
        ):
            if auth:
                user, api_key = auth
                # Return user-specific tools
            else:
                # Return public tools
            pass

    Returns:
        tuple: (User, APIKey) or None
    """
    # Try JWT from cookie if header not present
    if not credentials and access_token:
        user = await auth_service.get_user_from_token(access_token)
        if user:
            return user, None

    try:
        return await get_current_user(credentials, authorization, auth_service)
    except HTTPException:
        return None


# ===== Edition Guards =====

def require_saas():
    """
    Dependency to require SaaS edition.

    Use this to protect endpoints that should only be available
    on the Cloud SaaS platform (bigmcp.cloud).

    Usage:
        @app.get("/licenses/generate")
        async def generate_license(
            _: None = Depends(require_saas()),
            user: User = Depends(get_current_user_jwt)
        ):
            # Only available on SaaS
            pass

    Raises:
        HTTPException: 403 if not running on SaaS edition
    """
    from ..core.edition import is_saas

    async def check_saas():
        if not is_saas():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This feature is only available on bigmcp.cloud"
            )
        return None

    return check_saas


def require_enterprise_or_saas():
    """
    Dependency to require Enterprise or SaaS edition.

    Use for features available to paid customers (Enterprise license holders
    and SaaS subscribers) but not Community edition.

    Usage:
        @app.get("/advanced-feature")
        async def advanced_feature(
            _: None = Depends(require_enterprise_or_saas())
        ):
            pass

    Raises:
        HTTPException: 403 if running on Community edition
    """
    from ..core.edition import is_community

    async def check_edition():
        if is_community():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This feature requires Enterprise license or SaaS subscription. Visit bigmcp.cloud to upgrade."
            )
        return None

    return check_edition


# ===== Instance Admin Guard =====

async def require_instance_admin(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user)
) -> User:
    """
    Require current user to be an instance admin.

    Instance admins can:
    - Configure marketplace sources
    - Manage the local registry
    - Sync and curate marketplace
    - Access the admin interface

    The check depends on the current edition:
    - COMMUNITY: Always passes (single user = admin)
    - ENTERPRISE/CLOUD_SAAS: Checks user.preferences["instance_admin"]

    Usage:
        @app.post("/admin/marketplace/sources")
        async def add_source(
            admin_user: User = Depends(require_instance_admin)
        ):
            # Only instance admins can access
            pass

    Raises:
        HTTPException: 403 if user is not an instance admin
    """
    from ..core.instance_admin import is_instance_admin

    user, api_key = auth

    if not is_instance_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instance admin access required. Go to Settings to validate your admin token."
        )

    return user


async def get_instance_admin_optional(
    auth: Optional[tuple[User, Optional[APIKey]]] = Depends(get_current_user_optional)
) -> Optional[User]:
    """
    Get instance admin if authenticated as one, None otherwise.

    Useful for UI elements that should only be visible to instance admins.

    Usage:
        @app.get("/ui/config")
        async def get_ui_config(
            admin_user: Optional[User] = Depends(get_instance_admin_optional)
        ):
            return {
                "show_admin_menu": admin_user is not None
            }
    """
    from ..core.instance_admin import is_instance_admin

    if not auth:
        return None

    user, api_key = auth

    if is_instance_admin(user):
        return user

    return None
