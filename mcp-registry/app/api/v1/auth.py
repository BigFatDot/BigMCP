"""
Authentication endpoints - Login, register, token management.

Provides endpoints for user authentication with email/password.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.database import get_db
from ...models.user import User, AuthProvider, UserStatus
from ...models.api_key import APIKey
from ...models.organization import Organization, OrganizationMember, UserRole
from ...models.subscription import Subscription
from ...services.auth_service import AuthService
from ...schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
    RegisterResponse,
    RefreshTokenRequest,
    PasswordChange,
    ProfileUpdate,
    PasswordReset,
    PasswordResetConfirm,
    MFAChallengeResponse,
    MFALoginRequest
)
from ...core.config import settings
from ..dependencies import get_current_user_jwt, get_current_user, get_auth_service

# Security scheme for token extraction
bearer_scheme = HTTPBearer(auto_error=False)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user with email and password.

    Creates:
    - User account
    - Default organization for the user
    - Organization membership as admin
    - Auto-login: returns JWT tokens

    Returns:
        RegisterResponse: Created user information with access tokens
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if this is the first user (for auto-admin promotion)
    from ...core.edition import get_edition, Edition, get_max_users
    from sqlalchemy import func

    user_count_result = await db.execute(select(func.count(User.id)))
    user_count = user_count_result.scalar()
    is_first_user = user_count == 0

    # Edition-level seat cap. Community: 1 user. Enterprise/Cloud SaaS:
    # effectively unlimited (999999). Enforced at signup so the second
    # user is rejected with a clear message rather than silently created.
    max_users = get_max_users()
    if user_count >= max_users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This instance has reached its user limit "
                f"({max_users}). The Community edition is single-user; "
                "run the Enterprise edition or Cloud SaaS for multi-user."
            ),
        )

    # Hash password
    password_hash = auth_service.hash_password(data.password)

    # Create user (email_verified=False by default)
    user = User(
        email=data.email.lower(),
        name=data.name,
        auth_provider=AuthProvider.LOCAL,
        password_hash=password_hash,
        email_verified=False
    )
    # First user on the instance is auto-promoted to instance admin
    if is_first_user:
        user.preferences = {"instance_admin": True}

    db.add(user)
    await db.flush()  # Flush to get user.id

    # Create default organization for user
    org_name = f"{data.name}'s Organization" if data.name else f"{data.email}'s Organization"
    organization = Organization(
        name=org_name,
        slug=f"org-{user.id}",  # Simple slug based on user ID
        organization_type="personal"  # Personal organization type
    )
    db.add(organization)
    await db.flush()  # Flush to get organization.id

    # Create organization membership (user is admin of their own org)
    membership = OrganizationMember(
        user_id=user.id,
        organization_id=organization.id,
        role=UserRole.ADMIN
    )
    db.add(membership)

    await db.commit()
    await db.refresh(user)

    # Send verification email
    from ...models.email_verification_token import EmailVerificationToken
    from ...services.email_service import get_email_service
    import logging

    logger = logging.getLogger(__name__)

    verification_token, plaintext_token = EmailVerificationToken.create_token(
        user_id=user.id,
        email=user.email
    )
    db.add(verification_token)
    await db.commit()

    # Audit: account creation
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.USER_REGISTER,
            actor_id=user.id,
            organization_id=organization.id,
            resource_type="user",
            resource_id=str(user.id),
            details={
                "email": user.email,
                "auth_provider": "local",
                "is_first_user": is_first_user,
            },
            request=request,
        )
    except Exception:
        pass

    domain = settings.domain or "http://localhost:3000"
    verification_link = f"{domain}/verify-email?token={plaintext_token}"

    email_service = get_email_service()
    if email_service.is_configured:
        result = email_service.send_verification_email(
            to_email=user.email,
            verification_link=verification_link,
            user_name=user.name,
            expires_hours=48
        )
        if result.success:
            logger.info(f"Verification email sent to {user.email}")
        else:
            logger.error(f"Failed to send verification email to {user.email}: {result.error}")
    else:
        logger.warning(f"SMTP not configured, verification link for {user.email}: {verification_link}")

    # SaaS mode: require email verification before login
    # Return a specific response indicating verification needed (HTTP 202 Accepted)
    from ...core.edition import is_saas

    if is_saas():
        # SaaS: Don't auto-login, require email verification first
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "requires_verification": True,
                "message": "Account created! Please check your email to verify your address.",
                "email": user.email,
                # Include minimal user info (but no tokens)
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "name": user.name,
                    "email_verified": False
                }
            }
        )

    # Non-SaaS (Enterprise/Community): Auto-login as before
    access_token = auth_service.create_access_token(user.id, organization.id)
    refresh_token = auth_service.create_refresh_token(user.id)

    # Build user response with organization info
    user_response = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider.value if hasattr(user.auth_provider, 'value') else str(user.auth_provider),
        "email_verified": user.email_verified,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "slug": organization.slug
        }
    }

    return RegisterResponse(
        user=user_response,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/login")
async def login(
    data: UserLogin,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email and password.

    For SaaS mode: requires email verification before login.
    For MFA-enabled accounts: requires mfa_code or returns MFAChallengeResponse.

    Returns:
        TokenResponse: JWT access and refresh tokens
        OR MFAChallengeResponse: If MFA is required
    """
    # Force-SSO-only gate (Story I.1): if the instance admin has flipped
    # the toggle, refuse local-password login outright. Break-glass admins
    # are exempted only via the bootstrap check at toggle-enable time —
    # we don't carry a separate "this user is exempt" flag.
    from ...models.instance_settings import InstanceSettings
    settings_row = await db.get(InstanceSettings, 1)
    if settings_row and (settings_row.client_control or {}).get("force_sso_only"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "force_sso_only",
                "message": (
                    "Local password login is disabled on this instance. "
                    "Please use Single Sign-On."
                ),
            },
        )

    # Authenticate user
    user = await auth_service.authenticate_user(data.email, data.password)

    if not user:
        # Audit: failed login attempt
        try:
            from ...services.audit_service import AuditService
            from ...models.audit_log import AuditAction
            await AuditService(db).log_action(
                action=AuditAction.LOGIN_FAILED,
                actor_id=None,
                organization_id=None,
                resource_type="user",
                resource_id=None,
                details={"email": data.email, "reason": "invalid_credentials"},
                request=request,
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # SaaS mode: require email verification
    from ...core.edition import is_saas
    if is_saas() and not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "email_not_verified",
                "message": "Please verify your email address before logging in. Check your inbox for the verification link.",
                "email": user.email
            }
        )

    # Lifecycle gate (N1.4): suspended/deleted accounts cannot log in.
    if user.status != UserStatus.ACTIVE.value:
        # Audit the blocked attempt before raising — admins need to see
        # access attempts on disabled accounts as part of offboarding review.
        try:
            from ...services.audit_service import AuditService
            from ...models.audit_log import AuditAction
            await AuditService(db).log_action(
                action=AuditAction.LOGIN_FAILED,
                actor_id=user.id,
                organization_id=None,
                resource_type="user",
                resource_id=str(user.id),
                details={
                    "email": user.email,
                    "reason": f"account_{user.status}",
                },
                request=request,
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": f"account_{user.status}",
                "message": (
                    "This account has been suspended."
                    if user.status == UserStatus.SUSPENDED.value
                    else "This account has been deleted."
                ),
            },
        )

    # Get user's organization (deterministic: oldest membership first)
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at.asc())
        .limit(1)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no organization"
        )

    # Check MFA requirement
    if user.mfa_enabled:
        if not data.mfa_code:
            # MFA required but no code provided - return challenge
            mfa_token = auth_service.create_mfa_token(user.id, membership.organization_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "mfa_required": True,
                    "mfa_token": mfa_token,
                    "message": "MFA verification required. Provide mfa_code to complete login."
                }
            )

        # Verify MFA code
        from ...services.mfa_service import MFAService
        mfa_service = MFAService(db)
        if not await mfa_service.verify_code(user.id, data.mfa_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_mfa_code",
                    "message": "Invalid MFA code. Please try again."
                }
            )

    # Create tokens
    access_token = auth_service.create_access_token(user.id, membership.organization_id)
    refresh_token = auth_service.create_refresh_token(user.id)

    # Audit: successful login
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.LOGIN_SUCCESS,
            actor_id=user.id,
            organization_id=membership.organization_id,
            resource_type="user",
            resource_id=str(user.id),
            details={"email": user.email, "mfa_used": bool(user.mfa_enabled)},
            request=request,
        )
    except Exception:
        pass

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/login/mfa", response_model=TokenResponse)
async def login_mfa(
    data: MFALoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete login with MFA code.

    Use this endpoint to complete login after receiving an MFAChallengeResponse.
    Requires the mfa_token from the challenge and a valid MFA code.

    Returns:
        TokenResponse: JWT access and refresh tokens
    """
    from uuid import UUID

    # Decode MFA token
    payload = auth_service.decode_token(data.mfa_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA token"
        )

    # Verify token type
    if payload.get("type") != "mfa_challenge":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = UUID(payload.get("sub"))
    org_id = UUID(payload.get("org_id"))

    # Verify MFA code
    from ...services.mfa_service import MFAService
    mfa_service = MFAService(db)
    if not await mfa_service.verify_code(user_id, data.mfa_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_mfa_code",
                "message": "Invalid MFA code. Please try again."
            }
        )

    # Create tokens
    access_token = auth_service.create_access_token(user_id, org_id)
    refresh_token = auth_service.create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    Returns:
        TokenResponse: New access and refresh tokens
    """
    # Decode refresh token
    payload = auth_service.decode_token(data.refresh_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Verify token type
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    # Get user
    from uuid import UUID
    user_id = UUID(payload.get("sub"))
    result = await db.execute(
        select(User)
        .options(selectinload(User.organization_memberships))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Lifecycle gate (N1.4): refuse refresh for non-active accounts.
    if user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is not active",
        )

    # Cross-surface kill switch (N1.3): refuse refresh tokens issued
    # before the bulk revocation timestamp.
    if user.tokens_revoked_at:
        iat = payload.get("iat")
        if iat:
            from datetime import datetime as _dt
            token_issued_at = _dt.utcfromtimestamp(iat)
            revoked_at = (
                user.tokens_revoked_at.replace(tzinfo=None)
                if user.tokens_revoked_at.tzinfo
                else user.tokens_revoked_at
            )
            if token_issued_at < revoked_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked",
                )

    # Preserve organization context from the refresh token
    org_id = None
    org_id_from_token = payload.get("org_id")

    if org_id_from_token:
        # Validate user is still a member of that org
        from uuid import UUID as _UUID
        org_uuid = _UUID(org_id_from_token)
        is_still_member = any(
            m.organization_id == org_uuid
            for m in user.organization_memberships
        )
        if is_still_member:
            org_id = org_uuid

    # Fallback: single membership = no ambiguity
    if not org_id and len(user.organization_memberships) == 1:
        org_id = user.organization_memberships[0].organization_id

    # Fallback: multiple orgs, context lost
    if not org_id and user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization context lost. Please login again to select an organization."
        )

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no organization"
        )

    # Create new tokens preserving org context
    access_token = auth_service.create_access_token(user.id, org_id)
    new_refresh_token = auth_service.create_refresh_token(user.id, org_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me")
async def get_me(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current authenticated user information.

    Requires: Valid JWT access token OR API key

    Returns:
        Dict with user, organization, and subscription information
    """
    user, api_key = auth

    # Determine current organization context
    # Priority: 1) API key org  2) JWT org_id  3) oldest membership fallback
    target_org_id = None

    # 1. API key: organization is fixed by the key
    if api_key:
        target_org_id = str(api_key.organization_id)

    # 2. JWT: extract org_id from token payload
    if not target_org_id:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            payload = AuthService.decode_token(token)
            if payload:
                target_org_id = payload.get("org_id")

    # Get organization based on resolved org_id
    membership = None
    if target_org_id:
        result = await db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user.id)
            .where(OrganizationMember.organization_id == target_org_id)
            .options(selectinload(OrganizationMember.organization))
        )
        membership = result.scalar_one_or_none()

    # 3. Fallback: oldest membership (deterministic)
    if not membership:
        result = await db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user.id)
            .options(selectinload(OrganizationMember.organization))
            .order_by(OrganizationMember.created_at)
            .limit(1)
        )
        membership = result.scalar_one_or_none()

    # Get ALL organization memberships for role checking
    all_memberships_result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at)
    )
    all_memberships = all_memberships_result.scalars().all()

    # Build user response
    user_dict = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider.value if hasattr(user.auth_provider, 'value') else str(user.auth_provider),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        # Surfaced for the frontend to gate admin nav links on /auth/me
        # without an extra round-trip to /admin/status.
        "is_instance_admin": bool((user.preferences or {}).get("instance_admin")),
        "organization_memberships": [
            {
                "id": str(m.id),
                "organization_id": str(m.organization_id),
                "user_id": str(m.user_id),
                "role": m.role.value if hasattr(m.role, 'value') else str(m.role),
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in all_memberships
        ] if all_memberships else [],
    }

    # Build organization response
    organization_dict = None
    subscription_dict = None

    if membership and membership.organization:
        org = membership.organization
        organization_dict = {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug
        }

        # Get subscription for the organization
        sub_result = await db.execute(
            select(Subscription)
            .where(Subscription.organization_id == org.id)
            .limit(1)
        )
        subscription = sub_result.scalar_one_or_none()

        if subscription:
            subscription_dict = {
                "id": str(subscription.id),
                "tier": subscription.tier.value if hasattr(subscription.tier, 'value') else str(subscription.tier),
                "status": subscription.status.value if hasattr(subscription.status, 'value') else str(subscription.status),
                "is_active": subscription.status.value == "active" if hasattr(subscription.status, 'value') else subscription.status == "active",
                "max_users": subscription.max_users,
                "current_period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
                "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
                "trial_ends_at": subscription.trial_ends_at.isoformat() if subscription.trial_ends_at else None,
                "is_trial": subscription.trial_ends_at is not None,
                "cancel_at_period_end": subscription.cancel_at_period_end,
            }

    return {
        "user": user_dict,
        "organization": organization_dict,
        "subscription": subscription_dict
    }


@router.post("/switch-organization")
async def switch_organization(
    organization_id: str,
    user: User = Depends(get_current_user_jwt),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Switch to a different organization.

    Generates new tokens with the selected organization.
    User must be a member of the organization.

    Args:
        organization_id: UUID of the organization to switch to

    Returns:
        TokenResponse: New JWT tokens with the selected organization
    """
    from uuid import UUID

    # Validate organization_id format
    try:
        org_uuid = UUID(organization_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format"
        )

    # Verify user is a member of this organization
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .where(OrganizationMember.organization_id == org_uuid)
        .options(selectinload(OrganizationMember.organization))
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization"
        )

    # Generate new tokens with the selected organization
    access_token = auth_service.create_access_token(user.id, org_uuid)
    refresh_token = auth_service.create_refresh_token(user.id, org_uuid)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "organization": {
            "id": str(membership.organization.id),
            "name": membership.organization.name,
            "slug": membership.organization.slug
        }
    }


@router.get("/organizations")
async def list_user_organizations(
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db)
):
    """
    List all organizations the current user belongs to.

    Returns:
        List of organizations with membership details
    """
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .options(selectinload(OrganizationMember.organization))
        .order_by(OrganizationMember.created_at)
    )
    memberships = result.scalars().all()

    return {
        "organizations": [
            {
                "id": str(m.organization.id),
                "name": m.organization.name,
                "slug": m.organization.slug,
                "organization_type": m.organization.organization_type,
                "role": m.role.value if hasattr(m.role, 'value') else str(m.role),
                "joined_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in memberships
        ]
    }


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: PasswordChange,
    user: User = Depends(get_current_user_jwt),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Change current user's password.

    Requires: Valid JWT access token

    Returns:
        204 No Content on success
    """
    # Verify user uses local auth (not SSO)
    if user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change password for SSO users"
        )

    # Verify old password
    if not auth_service.verify_password(data.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Update password
    user.password_hash = auth_service.hash_password(data.new_password)
    await db.commit()

    return None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    user: User = Depends(get_current_user_jwt),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout current user by blacklisting the current token.

    The token will be immediately invalidated and cannot be used again.

    Returns:
        204 No Content
    """
    from ...services.token_blacklist_service import TokenBlacklistService
    from ...models.token_blacklist import BlacklistReason
    from datetime import datetime

    # Get token from credentials
    if not credentials:
        return None

    token = credentials.credentials
    payload = auth_service.decode_token(token)

    if payload:
        jti = payload.get("jti")
        exp = payload.get("exp")

        if jti and exp:
            # Convert exp timestamp to datetime
            expires_at = datetime.utcfromtimestamp(exp)

            # Add token to blacklist
            blacklist_service = TokenBlacklistService(db)
            await blacklist_service.blacklist_token(
                jti=jti,
                user_id=user.id,
                token_type="access",
                expires_at=expires_at,
                reason=BlacklistReason.LOGOUT
            )

            # Invalidate user tool cache on logout
            from ...services.user_tool_cache import get_user_tool_cache
            tool_cache = get_user_tool_cache()
            await tool_cache.invalidate(user.id)

    # Audit: logout
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.LOGOUT,
            actor_id=user.id,
            organization_id=None,
            resource_type="user",
            resource_id=str(user.id),
            details={"email": user.email},
            request=request,
        )
    except Exception:
        pass

    return None


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile.

    Requires: Valid JWT access token

    Returns:
        UserResponse: Updated user information
    """
    # Update fields if provided
    if data.name is not None:
        user.name = data.name

    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url

    await db.commit()
    await db.refresh(user)

    # Get user's organization
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .options(selectinload(OrganizationMember.organization))
        .order_by(OrganizationMember.created_at)
        .limit(1)
    )
    membership = result.scalar_one_or_none()

    # Build response
    user_dict = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "organization": None
    }

    if membership and membership.organization:
        org = membership.organization
        user_dict["organization"] = {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug
        }

    return user_dict


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    data: PasswordReset,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Request a password reset email.

    Sends a password reset link to the user's email if the account exists.
    Always returns 200 to prevent email enumeration attacks.

    Returns:
        Success message (regardless of whether email exists)
    """
    from ...models.password_reset_token import PasswordResetToken
    from ...services.email_service import get_email_service
    import logging

    logger = logging.getLogger(__name__)

    # Find user by email
    result = await db.execute(
        select(User).where(User.email == data.email.lower())
    )
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    success_response = {
        "message": "If an account exists with this email, a password reset link has been sent."
    }

    if not user:
        logger.info(f"Password reset requested for non-existent email: {data.email}")
        return success_response

    # Check if user uses local auth (not SSO)
    if user.password_hash is None:
        logger.info(f"Password reset requested for SSO user: {data.email}")
        return success_response

    # Invalidate any existing reset tokens for this user
    from datetime import datetime
    existing_tokens_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None)
        )
    )
    existing_tokens = existing_tokens_result.scalars().all()
    for token in existing_tokens:
        token.used_at = datetime.utcnow()

    # Get request metadata
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Create new reset token
    reset_token, plaintext_token = PasswordResetToken.create_token(
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent
    )
    db.add(reset_token)
    await db.commit()

    # Audit: password reset requested
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.PASSWORD_RESET_REQUEST,
            actor_id=user.id,
            organization_id=None,
            resource_type="user",
            resource_id=str(user.id),
            details={"email": user.email},
            request=request,
        )
    except Exception:
        pass

    # Build reset link
    domain = settings.domain or "http://localhost:3000"
    reset_link = f"{domain}/reset-password?token={plaintext_token}"

    # Send email
    email_service = get_email_service()
    if email_service.is_configured:
        result = email_service.send_password_reset_email(
            to_email=user.email,
            reset_link=reset_link,
            user_name=user.name,
            expires_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        if result.success:
            logger.info(f"Password reset email sent to {user.email}")
        else:
            logger.error(f"Failed to send password reset email to {user.email}: {result.error}")
    else:
        logger.warning(f"SMTP not configured, password reset link for {user.email}: {reset_link}")

    return success_response


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    data: PasswordResetConfirm,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password using a valid reset token.

    Verifies the token and updates the user's password.

    Returns:
        Success message on password reset
    """
    from ...models.password_reset_token import PasswordResetToken
    import logging

    logger = logging.getLogger(__name__)

    # Hash the provided token and find it
    token_hash = PasswordResetToken.hash_token(data.token)

    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Check if token is valid (not used, not expired)
    if not reset_token.is_valid:
        if reset_token.is_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link has already been used"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link has expired"
            )

    # Get the user
    user_result = await db.execute(
        select(User).where(User.id == reset_token.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )

    # Update password
    user.password_hash = auth_service.hash_password(data.new_password)

    # Mark token as used
    reset_token.mark_used()

    await db.commit()

    logger.info(f"Password reset successful for user {user.email}")

    # Audit: password reset confirmed
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.PASSWORD_RESET_CONFIRM,
            actor_id=user.id,
            organization_id=None,
            resource_type="user",
            resource_id=str(user.id),
            details={"email": user.email},
            request=request,
        )
    except Exception:
        pass

    return {"message": "Password has been reset successfully. You can now log in with your new password."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(
    token: str,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify email address using a verification token.

    Marks the user's email as verified and returns JWT tokens for auto-login.
    This creates a seamless flow: signup → email → click link → verified & logged in.

    Returns:
        Success message with JWT tokens for auto-login
    """
    from ...models.email_verification_token import EmailVerificationToken
    import logging

    logger = logging.getLogger(__name__)

    # Hash the provided token and find it
    token_hash = EmailVerificationToken.hash_token(token)

    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash
        )
    )
    verification_token = result.scalar_one_or_none()

    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    # Check if token is valid (not used, not expired)
    if not verification_token.is_valid:
        if verification_token.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email has already been verified"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification link has expired. Please request a new one."
            )

    # Get the user with organization memberships
    user_result = await db.execute(
        select(User)
        .options(selectinload(User.organization_memberships))
        .where(User.id == verification_token.user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )

    # Verify email matches (in case user changed email)
    if user.email.lower() != verification_token.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is for a different email address"
        )

    # Mark email as verified
    user.email_verified = True
    verification_token.mark_verified()

    # SaaS: auto-create 30-day free trial subscription
    from ...core.edition import is_saas
    if is_saas():
        from ...models.subscription import Subscription, SubscriptionTier, SubscriptionStatus
        from datetime import timedelta
        import uuid

        # Find user's organization
        membership_for_trial = None
        if user.organization_memberships:
            membership_for_trial = sorted(
                user.organization_memberships,
                key=lambda m: m.created_at if m.created_at else datetime.min
            )[0]
        else:
            mem_result = await db.execute(
                select(OrganizationMember)
                .where(OrganizationMember.user_id == user.id)
                .limit(1)
            )
            membership_for_trial = mem_result.scalar_one_or_none()

        if membership_for_trial:
            # Check if subscription already exists for this org
            existing_sub = await db.execute(
                select(Subscription).where(
                    Subscription.organization_id == membership_for_trial.organization_id
                )
            )
            if not existing_sub.scalar_one_or_none():
                now = datetime.now(tz=datetime.now().astimezone().tzinfo)
                trial_end = now + timedelta(days=30)
                trial_sub = Subscription(
                    organization_id=membership_for_trial.organization_id,
                    tier=SubscriptionTier.TEAM,
                    status=SubscriptionStatus.TRIALING,
                    max_users=0,  # 0 = unlimited
                    lemonsqueezy_subscription_id=f"demo-trial-{uuid.uuid4().hex[:12]}",
                    current_period_start=now,
                    current_period_end=trial_end,
                    trial_ends_at=trial_end,
                    subscription_metadata={"source": "auto_trial", "demo_platform": True}
                )
                db.add(trial_sub)
                logger.info(f"Auto-created 30-day demo trial for user {user.email}")

    await db.commit()

    logger.info(f"Email verified for user {user.email}")

    # Get user's organization for token generation (deterministic: oldest first)
    org_id = None
    if user.organization_memberships:
        # Sort by created_at to get deterministic first org
        sorted_memberships = sorted(
            user.organization_memberships,
            key=lambda m: m.created_at if m.created_at else datetime.min
        )
        org_id = sorted_memberships[0].organization_id
    else:
        # Fallback: query for organization
        membership_result = await db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user.id)
            .order_by(OrganizationMember.created_at.asc())
            .limit(1)
        )
        membership = membership_result.scalar_one_or_none()
        if membership:
            org_id = membership.organization_id

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no organization"
        )

    # Generate tokens for auto-login
    access_token = auth_service.create_access_token(user.id, org_id)
    refresh_token = auth_service.create_refresh_token(user.id)

    return {
        "message": "Email verified successfully. You are now logged in.",
        "verified": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db)
):
    """
    Resend email verification link.

    Requires: Valid JWT access token

    Returns:
        Success message
    """
    from ...models.email_verification_token import EmailVerificationToken
    from ...services.email_service import get_email_service
    from datetime import datetime
    import logging

    logger = logging.getLogger(__name__)

    # Check if already verified
    if user.email_verified:
        return {"message": "Email is already verified."}

    # Invalidate existing verification tokens for this user
    existing_tokens_result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.verified_at.is_(None)
        )
    )
    existing_tokens = existing_tokens_result.scalars().all()
    for token in existing_tokens:
        token.verified_at = datetime.utcnow()  # Mark as used

    # Create new verification token
    verification_token, plaintext_token = EmailVerificationToken.create_token(
        user_id=user.id,
        email=user.email
    )
    db.add(verification_token)
    await db.commit()

    # Send verification email
    domain = settings.domain or "http://localhost:3000"
    verification_link = f"{domain}/verify-email?token={plaintext_token}"

    email_service = get_email_service()
    if email_service.is_configured:
        result = email_service.send_verification_email(
            to_email=user.email,
            verification_link=verification_link,
            user_name=user.name,
            expires_hours=48
        )
        if result.success:
            logger.info(f"Verification email resent to {user.email}")
        else:
            logger.error(f"Failed to resend verification email to {user.email}: {result.error}")
    else:
        logger.warning(f"SMTP not configured, verification link for {user.email}: {verification_link}")

    return {"message": "Verification email sent. Please check your inbox."}


@router.post("/resend-verification-public", status_code=status.HTTP_200_OK)
async def resend_verification_public(
    email: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Resend email verification link (public endpoint, no auth required).

    This allows users who signed up but can't login (because email not verified)
    to request a new verification email.

    Always returns 200 to prevent email enumeration attacks.

    Returns:
        Success message (regardless of whether email exists or is already verified)
    """
    from ...models.email_verification_token import EmailVerificationToken
    from ...services.email_service import get_email_service
    from datetime import datetime
    import logging

    logger = logging.getLogger(__name__)

    # Generic success response to prevent enumeration
    success_response = {"message": "If an account exists with this email, a verification link has been sent."}

    # Find user by email
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.info(f"Verification resend requested for non-existent email: {email}")
        return success_response

    # Check if already verified
    if user.email_verified:
        logger.info(f"Verification resend requested for already verified email: {email}")
        return success_response

    # Invalidate existing verification tokens for this user
    existing_tokens_result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.verified_at.is_(None)
        )
    )
    existing_tokens = existing_tokens_result.scalars().all()
    for token in existing_tokens:
        token.verified_at = datetime.utcnow()  # Mark as used

    # Create new verification token
    verification_token, plaintext_token = EmailVerificationToken.create_token(
        user_id=user.id,
        email=user.email
    )
    db.add(verification_token)
    await db.commit()

    # Send verification email
    domain = settings.domain or "http://localhost:3000"
    verification_link = f"{domain}/verify-email?token={plaintext_token}"

    email_service = get_email_service()
    if email_service.is_configured:
        result = email_service.send_verification_email(
            to_email=user.email,
            verification_link=verification_link,
            user_name=user.name,
            expires_hours=48
        )
        if result.success:
            logger.info(f"Verification email resent to {user.email}")
        else:
            logger.error(f"Failed to resend verification email to {user.email}: {result.error}")
    else:
        logger.warning(f"SMTP not configured, verification link for {user.email}: {verification_link}")

    return success_response


# ---------------------------------------------------------------------------
# Connected apps (Story H / N2.4) — list & revoke OAuth grants per client.
# ---------------------------------------------------------------------------


@router.get("/connected-apps")
async def list_connected_apps(
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db),
):
    """List the OAuth clients currently connected to the caller's account.

    Aggregates active ``oauth_sessions`` rows by client so the user sees
    one row per app rather than one per token issuance. Sessions revoked
    by the user (or invalidated by a global kill switch) are excluded.
    """
    from sqlalchemy import func
    from ...models.oauth_session import OAuthSession
    from ...models.oauth import OAuthClient

    rows = await db.execute(
        select(
            OAuthClient.id,
            OAuthClient.client_id,
            OAuthClient.name,
            OAuthClient.description,
            OAuthClient.cimd_url,
            OAuthClient.registration_method,
            func.count(OAuthSession.id).label("session_count"),
            func.min(OAuthSession.created_at).label("first_authorized_at"),
            func.max(
                func.coalesce(OAuthSession.last_seen_at, OAuthSession.created_at)
            ).label("last_seen_at"),
        )
        .join(OAuthSession, OAuthSession.oauth_client_id == OAuthClient.id)
        .where(OAuthSession.user_id == user.id)
        .where(OAuthSession.revoked_at.is_(None))
        .group_by(
            OAuthClient.id,
            OAuthClient.client_id,
            OAuthClient.name,
            OAuthClient.description,
            OAuthClient.cimd_url,
            OAuthClient.registration_method,
        )
        .order_by(func.max(
            func.coalesce(OAuthSession.last_seen_at, OAuthSession.created_at)
        ).desc())
    )

    apps = []
    for row in rows.all():
        apps.append({
            "client_uuid": str(row.id),
            "client_id": row.client_id,
            "name": row.name,
            "description": row.description,
            "cimd_url": row.cimd_url,
            "registration_method": row.registration_method,
            "session_count": int(row.session_count or 0),
            "first_authorized_at": (
                row.first_authorized_at.isoformat()
                if row.first_authorized_at else None
            ),
            "last_seen_at": (
                row.last_seen_at.isoformat() if row.last_seen_at else None
            ),
        })

    return {"connected_apps": apps}


@router.delete("/connected-apps/{client_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_connected_app(
    client_uuid: str,
    request: Request,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Revoke every active session the caller has with one OAuth client.

    Per-client surgical revocation:

    1. Mark every active ``oauth_sessions`` row for this user × client
       as revoked — the row keeps the audit trail.
    2. Blacklist the access_token_jti and refresh_token_jti captured at
       grant time, so the client's outstanding JWTs become 401 on next
       use — without touching ``user.tokens_revoked_at`` (that would
       also kill the user's own browser session, since the kill switch
       is user-wide).
    """
    from uuid import UUID
    from datetime import datetime as _dt, timedelta
    from ...models.oauth_session import OAuthSession
    from ...models.oauth import OAuthClient
    from ...services.audit_service import AuditService
    from ...services.token_blacklist_service import TokenBlacklistService
    from ...models.token_blacklist import BlacklistReason
    from ...models.audit_log import AuditAction
    from ...core.config import settings as core_settings

    try:
        client_uuid_obj = UUID(client_uuid)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client UUID",
        )

    # Verify the client exists (404 instead of 204 if the user invents an UUID)
    client_q = await db.execute(
        select(OAuthClient).where(OAuthClient.id == client_uuid_obj)
    )
    client_row = client_q.scalar_one_or_none()
    if client_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # Pull active sessions for this user × client
    sessions_q = await db.execute(
        select(OAuthSession)
        .where(OAuthSession.user_id == user.id)
        .where(OAuthSession.oauth_client_id == client_uuid_obj)
        .where(OAuthSession.revoked_at.is_(None))
    )
    sessions = list(sessions_q.scalars().all())

    if not sessions:
        # Nothing to revoke. Surface 404 so the caller doesn't get the
        # impression that revocation succeeded for an unknown app.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active sessions for this client",
        )

    blacklist = TokenBlacklistService(db)
    # Conservative natural expiry — the in-memory cache will keep the
    # JTI until at least the token's max lifetime. Pick refresh-token
    # lifetime so we cover both surfaces from the same JTI set.
    natural_expiry = _dt.utcnow() + timedelta(
        days=core_settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    revoked_count = 0
    for sess in sessions:
        sess.revoke(reason="user_revoke")
        for jti, ttype in (
            (sess.access_token_jti, "access"),
            (sess.refresh_token_jti, "refresh"),
        ):
            if jti:
                await blacklist.blacklist_token(
                    jti=jti,
                    user_id=user.id,
                    token_type=ttype,
                    expires_at=natural_expiry,
                    reason=BlacklistReason.LOGOUT,
                )
        revoked_count += 1

    await db.commit()

    # Audit
    try:
        await AuditService(db).log_action(
            action=AuditAction.CONNECTED_APP_REVOKE,
            actor_id=user.id,
            organization_id=None,
            resource_type="oauth_client",
            resource_id=str(client_uuid_obj),
            details={
                "client_id": client_row.client_id,
                "client_name": client_row.name,
                "sessions_revoked": revoked_count,
            },
            request=request,
        )
    except Exception:
        pass

    return None


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete current user's account.

    This is a destructive operation that:
    - Deletes the user account
    - Cascades to delete organization memberships
    - Cascades to delete API keys
    - Cascades to delete user credentials

    Requires: Valid JWT access token

    Returns:
        204 No Content on success
    """
    # Delete user (cascades are set up in the model)
    await db.delete(user)
    await db.commit()

    return None
