"""
OAuth 2.0 endpoints - Authorization Code Flow for Claude Desktop.

Implements OAuth 2.0 Authorization Code Flow with PKCE support.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode


def _oauth_invalid_request(description: str) -> JSONResponse:
    """
    Build a 400 ``invalid_request`` JSON response per RFC 6749 §5.2.

    Used by the OAuth endpoints when state/PKCE pre-flight checks fail —
    a misbehaving client must never see the HTML login/consent pages.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "invalid_request",
            "error_description": description,
        },
    )


def _validate_oauth_security_params(
    state: Optional[str],
    code_challenge: Optional[str],
    code_challenge_method: Optional[str],
) -> Optional[JSONResponse]:
    """
    Enforce mandatory CSRF + PKCE parameters on the authorization request.

    - ``state`` is REQUIRED (RFC 6749 §10.12 — CSRF protection)
    - ``code_challenge`` is REQUIRED (RFC 7636 — PKCE)
    - ``code_challenge_method`` must be ``S256`` (the ``plain`` method
      is explicitly refused)

    Returns a JSONResponse on failure, or ``None`` if all checks pass.
    """
    if not state:
        return _oauth_invalid_request(
            "state is required (RFC 6749 §10.12)"
        )
    if not code_challenge:
        return _oauth_invalid_request(
            "PKCE code_challenge is required (RFC 7636)"
        )
    if code_challenge_method != "S256":
        return _oauth_invalid_request(
            "Only S256 code_challenge_method is supported"
        )
    return None

from ...db.database import get_db
from ...models.user import User
from ...models.organization import OrganizationMember
from ...models.subscription import Subscription, SubscriptionTier
from ...services.oauth_service import OAuthService
from ...services.auth_service import AuthService
from ...schemas.oauth import (
    OAuthClientCreate,
    OAuthClientResponse,
    AuthorizationRequest,
    TokenRequest,
    TokenResponse,
    DynamicClientRegistrationRequest,
    DynamicClientRegistrationResponse
)
from ..dependencies import get_current_user_jwt, get_current_user_optional
from ...middleware.feature_gate import require_subscription, get_current_subscription


router = APIRouter(prefix="/oauth", tags=["OAuth 2.0"])

# Templates will be initialized in main.py
templates: Optional[Jinja2Templates] = None


def get_oauth_service(db: AsyncSession = Depends(get_db)) -> OAuthService:
    """Dependency for OAuth service."""
    return OAuthService(db)


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Dependency for Auth service."""
    return AuthService(db)


# ===== Client Management =====

@router.post("/clients", response_model=OAuthClientResponse, status_code=status.HTTP_201_CREATED)
@require_subscription(tier=SubscriptionTier.TEAM)
async def create_oauth_client(
    data: OAuthClientCreate,
    request: Request,
    current_user: User = Depends(get_current_user_jwt),
    subscription: Subscription = Depends(get_current_subscription),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new OAuth client (Team tier only).

    This endpoint creates a new OAuth client for third-party applications
    like Claude Desktop to integrate with MCPHub.

    **Requires Team subscription tier.**

    **Returns client_secret ONLY on creation** - store it securely!

    Example response:
    ```json
    {
        "id": "...",
        "client_id": "client_abc123...",
        "client_secret": "secret_xyz789...",  // ONLY returned here!
        "name": "Claude Desktop",
        "redirect_uris": ["https://claude.ai/api/oauth/callback"],
        "allowed_scopes": ["mcp:execute", "mcp:read"]
    }
    ```
    """

    client = await oauth_service.create_client(
        name=data.name,
        redirect_uris=data.redirect_uris,
        description=data.description,
        allowed_scopes=data.allowed_scopes,
        is_trusted=data.is_trusted
    )

    # Audit: manual OAuth client creation
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.OAUTH_CLIENT_CREATE,
            actor_id=current_user.id,
            organization_id=None,
            resource_type="oauth_client",
            resource_id=str(client.id),
            details={
                "client_id": client.client_id,
                "name": client.name,
                "redirect_uris": data.redirect_uris,
                "is_trusted": data.is_trusted,
            },
            request=request,
        )
    except Exception:
        pass

    # Convert to response model with plaintext secret
    response = OAuthClientResponse.from_orm(client)
    response.client_secret = client.plaintext_secret

    return response


# ===== Dynamic Client Registration (RFC 7591) =====

@router.post(
    "/register",
    response_model=DynamicClientRegistrationResponse,
    response_model_exclude_none=True,  # Fix mcp-remote Zod validation errors
    status_code=status.HTTP_201_CREATED
)
async def dynamic_client_registration(
    data: DynamicClientRegistrationRequest,
    request: Request,
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Dynamic Client Registration endpoint (RFC 7591).

    Allows OAuth clients like Claude Desktop to automatically register
    and obtain client credentials without manual intervention.

    **Flow**:
    1. Claude Desktop discovers this endpoint via `/.well-known/oauth-authorization-server`
    2. Claude POSTs registration request with metadata
    3. Server creates OAuth client and returns `client_id` + `client_secret`
    4. Claude uses these credentials for the authorization flow

    **Request**:
    ```json
    {
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "client_name": "Claude",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": "mcp:execute mcp:read"
    }
    ```

    **Response**:
    ```json
    {
        "client_id": "client_abc123...",
        "client_secret": "secret_xyz789...",
        "client_id_issued_at": 1640000000,
        "client_secret_expires_at": 0,
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": "mcp:execute mcp:read"
    }
    ```

    **Note**: No authentication required for registration (RFC 7591 recommendation).
    Servers MAY rate-limit unauthenticated registration requests.
    """
    import time

    # Parse scope string for echo response
    requested_scopes = data.scope.split() if data.scope else ["mcp:execute", "mcp:read"]

    # DCR clients always get all supported scopes as allowed_scopes
    # This allows clients to request any subset during authorization
    all_supported_scopes = ["mcp:execute", "mcp:read", "mcp:write", "offline_access"]

    # ----- N2.2 client control + CIMD ---------------------------------------
    # Resolve the effective instance policy. We don't know which org
    # the requesting client targets at DCR time (it's a pre-flow), so
    # the policy is read at instance level only — org overrides apply
    # at /authorize.
    from ...services.policy_resolver import PolicyResolver
    from ...services.cimd_service import (
        CIMDService,
        CIMDError,
        is_https_url,
    )
    from ...models.oauth import (
        OAuthClientApprovalStatus,
        OAuthClientRegistrationMethod,
    )
    from ...models.audit_log import AuditAction
    from ...services.audit_service import AuditService

    policy = await PolicyResolver(db).get_instance_policy()

    if policy.enabled and policy.dcr_policy == "denied":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dynamic Client Registration is disabled by instance policy.",
        )

    # Decide whether this DCR is a CIMD registration (SEP-991).
    cimd_url: Optional[str] = data.client_id_metadata_document
    cimd_doc: Optional[dict] = None

    if cimd_url:
        try:
            async with CIMDService() as cimd:
                cimd_doc = await cimd.fetch_and_validate(cimd_url)
            try:
                await AuditService(db).log_action(
                    action=AuditAction.OAUTH_CIMD_FETCH,
                    actor_id=None,
                    organization_id=None,
                    resource_type="oauth_client",
                    resource_id=cimd_url,
                    details={
                        "client_name": cimd_doc.get("client_name"),
                        "redirect_uris": cimd_doc.get("redirect_uris"),
                    },
                    request=request,
                )
            except Exception:
                pass
        except CIMDError as exc:
            try:
                await AuditService(db).log_action(
                    action=AuditAction.OAUTH_CIMD_FETCH_FAILED,
                    actor_id=None,
                    organization_id=None,
                    resource_type="oauth_client",
                    resource_id=cimd_url,
                    details={"error": str(exc)},
                    request=request,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid CIMD: {exc}",
            )
    elif policy.enabled and policy.require_cimd:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Instance policy requires Client ID Metadata Document; "
                "supply client_id_metadata_document in the request body."
            ),
        )

    # Decide registration_method + approval_status from the policy.
    if cimd_url:
        registration_method = OAuthClientRegistrationMethod.CIMD.value
        # Auto-approve only if the policy allows it AND the CIMD URL
        # is on the trusted list (or trusted list is empty meaning
        # "trust any valid CIMD" when auto_approve_cimd is True).
        if policy.auto_approve_cimd and (
            not policy.trusted_cimd_urls
            or cimd_url in set(policy.trusted_cimd_urls)
        ):
            approval_status = OAuthClientApprovalStatus.AUTO_APPROVED.value
        else:
            approval_status = OAuthClientApprovalStatus.PENDING.value
    elif policy.enabled and policy.dcr_policy == "admin_approval":
        registration_method = OAuthClientRegistrationMethod.DCR_APPROVED.value
        approval_status = OAuthClientApprovalStatus.PENDING.value
    else:
        registration_method = OAuthClientRegistrationMethod.DCR_OPEN.value
        approval_status = OAuthClientApprovalStatus.AUTO_APPROVED.value

    # CIMD wins for client_name + redirect_uris (the document is the
    # source of truth — the request body is treated as fallback).
    effective_name = (
        (cimd_doc.get("client_name") if cimd_doc else None)
        or data.client_name
        or "Dynamically Registered Client"
    )
    effective_redirect_uris = (
        (cimd_doc.get("redirect_uris") if cimd_doc else None)
        or data.redirect_uris
    )

    # Create OAuth client using the service
    client = await oauth_service.create_client(
        name=effective_name,
        redirect_uris=effective_redirect_uris,
        description=(
            f"CIMD: {cimd_url}"
            if cimd_url
            else f"Registered via DCR. Client URI: {data.client_uri or 'N/A'}"
        ),
        allowed_scopes=all_supported_scopes,
        is_trusted=False,  # DCR clients are not trusted by default
        registration_method=registration_method,
        approval_status=approval_status,
        cimd_url=cimd_url,
        cimd_metadata_cached=cimd_doc,
    )

    # Audit: Dynamic Client Registration (RFC 7591)
    try:
        await AuditService(db).log_action(
            action=AuditAction.OAUTH_CLIENT_REGISTER,
            actor_id=None,
            organization_id=None,
            resource_type="oauth_client",
            resource_id=str(client.id),
            details={
                "client_id": client.client_id,
                "client_name": effective_name,
                "client_uri": data.client_uri,
                "redirect_uris": effective_redirect_uris,
                "requested_scopes": requested_scopes,
                "grant_types": data.grant_types,
                "registration_method": registration_method,
                "approval_status": approval_status,
                "cimd_url": cimd_url,
            },
            request=request,
        )
    except Exception:
        pass

    # Get current timestamp
    current_time = int(time.time())

    # Build response according to RFC 7591
    return DynamicClientRegistrationResponse(
        client_id=client.client_id,
        client_secret=client.plaintext_secret,  # ONLY returned on registration!
        client_id_issued_at=current_time,
        client_secret_expires_at=0,  # 0 = never expires

        # Echo back the registered metadata
        redirect_uris=data.redirect_uris,
        token_endpoint_auth_method=data.token_endpoint_auth_method or "client_secret_post",
        grant_types=data.grant_types or ["authorization_code", "refresh_token"],
        response_types=data.response_types or ["code"],
        client_name=data.client_name,
        client_uri=data.client_uri,
        logo_uri=data.logo_uri,
        scope=" ".join(requested_scopes),  # Echo back what client requested
        contacts=data.contacts,
        tos_uri=data.tos_uri,
        policy_uri=data.policy_uri
    )


# ===== Authorization Flow =====

@router.post("/login")
async def oauth_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    # OAuth parameters to preserve
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scope: str = Form("mcp:execute"),
    state: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    auth_service: AuthService = Depends(get_auth_service),
    oauth_service: OAuthService = Depends(get_oauth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth login endpoint - authenticates user and redirects to authorize.

    Called by the OAuth login page when user submits credentials.
    Creates session cookie with JWT and redirects back to /authorize.

    ``state`` and ``code_challenge`` are REQUIRED (RFC 6749 §10.12 +
    RFC 7636). Only ``code_challenge_method=S256`` is accepted.
    """
    # Enforce CSRF + PKCE before doing any user lookup or auth work.
    security_error = _validate_oauth_security_params(
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    if security_error is not None:
        return security_error

    # Authenticate user
    user = await auth_service.authenticate_user(email, password)

    if not user:
        # Login failed - show login page again with error
        client = await oauth_service.get_client_by_id(client_id)

        if templates is None:
            raise HTTPException(
                status_code=500,
                detail="Templates not configured"
            )

        return templates.TemplateResponse(
            "oauth_login.html",
            {
                "request": request,
                "client_name": client.name if client else "Unknown Client",
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "error": "Invalid email or password"
            }
        )

    # Get user's organization
    from ...models.organization import OrganizationMember
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .limit(1)
    )
    membership = result.scalar_one_or_none()
    organization_id = membership.organization_id if membership else None

    # Create JWT access token
    access_token = auth_service.create_access_token(
        user_id=user.id,
        organization_id=organization_id
    )

    # Build redirect URL back to /authorize with all OAuth parameters
    from urllib.parse import urlencode
    params = {
        "response_type": response_type,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if state:
        params["state"] = state
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method

    authorize_url = f"/api/v1/oauth/authorize?{urlencode(params)}"

    # Create redirect response with session cookie
    response = RedirectResponse(url=authorize_url, status_code=303)

    # Set JWT in HTTPOnly cookie for session
    from ...core.config import settings as core_settings
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,      # Prevent JavaScript access
        secure=not core_settings.DEBUG,  # True in production (HTTPS), False in dev
        samesite="lax",     # CSRF protection
        max_age=1800,       # 30 minutes
        path="/"
    )

    return response


@router.get("/authorize", response_class=HTMLResponse)
async def authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "mcp:execute",
    state: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: str = "S256",
    prompt: Optional[str] = None,  # OAuth 2.0 prompt parameter: "login" forces re-auth
    current_user_tuple: Optional[tuple] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    OAuth authorization endpoint (Step 1).

    User is redirected here by the client (e.g., Claude Desktop).
    Shows login page if not authenticated, then consent page if authenticated.

    Flow:
    1. Client redirects user here with client_id, redirect_uri, etc.
    2. If user not logged in → Display login page
    3. After login → User sees consent page (if not trusted client)
    4. User approves → redirect to client with authorization code
    5. User denies → redirect to client with error

    Query Parameters:
    - response_type: Must be "code"
    - client_id: OAuth client ID
    - redirect_uri: Where to redirect after authorization
    - scope: Requested scopes (space-separated)
    - state: Client state for CSRF protection (REQUIRED, RFC 6749 §10.12)
    - code_challenge: PKCE code challenge (REQUIRED, RFC 7636)
    - code_challenge_method: PKCE method (must be S256; plain is refused)
    - prompt: "login" to force re-authentication, "consent" to always show consent

    Authorization: Optional - shows login page if not authenticated
    """
    # Validate response_type
    if response_type != "code":
        raise HTTPException(
            status_code=400,
            detail="Invalid response_type. Only 'code' is supported."
        )

    # Enforce CSRF + PKCE parameters before doing anything else. A
    # client that omits state or code_challenge is broken or hostile,
    # and must NEVER be shown the HTML login/consent pages.
    security_error = _validate_oauth_security_params(
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    if security_error is not None:
        return security_error

    # Get and validate OAuth client
    client = await oauth_service.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # N2.2 client-control gate: a PENDING or REJECTED client cannot
    # complete the authorize flow even if it managed to register.
    from ...models.oauth import OAuthClientApprovalStatus as _OACS
    if client.approval_status == _OACS.REJECTED.value:
        raise HTTPException(
            status_code=403,
            detail="This OAuth client has been rejected by the instance admin.",
        )
    if client.approval_status == _OACS.PENDING.value:
        raise HTTPException(
            status_code=403,
            detail=(
                "This OAuth client is awaiting admin approval. "
                "Contact your instance administrator."
            ),
        )

    # Validate redirect_uri
    if not oauth_service.validate_redirect_uri(client, redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    # Check if user is authenticated
    current_user = current_user_tuple[0] if current_user_tuple else None

    # If prompt=login, force showing login page regardless of session
    force_login = prompt == "login"

    # If user is NOT authenticated OR force_login, show login page
    if not current_user or force_login:
        if templates is None:
            raise HTTPException(
                status_code=500,
                detail="Templates not configured"
            )

        # Create response with login page
        response = templates.TemplateResponse(
            "oauth_login.html",
            {
                "request": request,
                "client_name": client.name,
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method
            }
        )
        # Clear any expired/invalid cookie to ensure fresh login
        response.delete_cookie(key="access_token", path="/")
        return response

    # Parse scopes
    requested_scopes = scope.split() if scope else ["mcp:execute"]

    # Validate scopes
    for requested_scope in requested_scopes:
        if requested_scope not in client.allowed_scopes:
            raise HTTPException(
                status_code=400,
                detail=f"Scope '{requested_scope}' not allowed for this client"
            )

    # If client is trusted, skip consent and immediately issue code
    if client.is_trusted:
        # Get user's first organization
        result = await db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == current_user.id)
            .limit(1)
        )
        membership = result.scalar_one_or_none()

        if not membership:
            raise HTTPException(status_code=400, detail="User has no organization")

        # Get organization
        from ...models.organization import Organization
        organization = await db.get(Organization, membership.organization_id)

        # Create authorization code
        auth_code = await oauth_service.create_authorization_code(
            client=client,
            user=current_user,
            organization=organization,
            redirect_uri=redirect_uri,
            scopes=requested_scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method
        )

        # Redirect to client with authorization code
        params = {"code": auth_code.code}
        if state:
            params["state"] = state

        redirect_url = f"{redirect_uri}?{urlencode(params)}"
        return RedirectResponse(url=redirect_url, status_code=303)

    # Display consent page
    if templates is None:
        raise HTTPException(
            status_code=500,
            detail="Templates not configured"
        )

    return templates.TemplateResponse(
        "oauth_consent.html",
        {
            "request": request,
            "client": client,
            "scopes": requested_scopes,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "user": current_user
        }
    )


@router.post("/authorize")
async def authorize_consent(
    request: Request,
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    scopes: str = Form(...),  # Comma-separated
    state: Optional[str] = Form(None),
    code_challenge: Optional[str] = Form(None),
    code_challenge_method: Optional[str] = Form("S256"),
    approved: str = Form(...),  # "true" or "false"
    access_token: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
    oauth_service: OAuthService = Depends(get_oauth_service)
):
    """
    Handle user consent (Step 2).

    Posted by the consent page form when user approves/denies.

    If approved:
    - Creates authorization code
    - Redirects to client with code

    If denied:
    - Redirects to client with error

    If session expired:
    - Clears expired cookie
    - Redirects back to GET /authorize to show login page
    """
    import logging
    logger = logging.getLogger("oauth")
    logger.info(f"🔍 POST /authorize called - access_token present: {access_token is not None}")

    # Helper function to redirect to login page when session is invalid/expired
    def redirect_to_login():
        """Build redirect URL back to GET /authorize (which will show login page)."""
        # Convert scopes back to space-separated format for URL
        scope_str = " ".join(scopes.split(",")) if scopes else "mcp:execute"
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope_str,
        }
        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method or "S256"

        authorize_url = f"/api/v1/oauth/authorize?{urlencode(params)}"
        response = RedirectResponse(url=authorize_url, status_code=303)
        # Clear the expired/invalid cookie
        response.delete_cookie(key="access_token", path="/")
        logger.info(f"🔄 Session expired - redirecting to login: {authorize_url}")
        return response

    # Verify JWT authentication from cookie
    if not access_token:
        logger.warning("⚠️ No access_token cookie found - redirecting to login")
        return redirect_to_login()

    logger.info(f"✅ access_token found, verifying...")
    current_user = await auth_service.get_user_from_token(access_token)
    if not current_user:
        logger.warning("⚠️ Invalid or expired token - redirecting to login")
        return redirect_to_login()

    logger.info(f"✅ User authenticated: {current_user.email}")

    # Get client
    logger.info(f"📝 Getting client: {client_id}")
    client = await oauth_service.get_client_by_id(client_id)
    if not client:
        logger.error(f"❌ Invalid client_id: {client_id}")
        raise HTTPException(status_code=400, detail="Invalid client_id")
    logger.info(f"✅ Client found: {client.name}")

    # Validate redirect_uri
    logger.info(f"📝 Validating redirect_uri: {redirect_uri}")
    if not oauth_service.validate_redirect_uri(client, redirect_uri):
        logger.error(f"❌ Invalid redirect_uri: {redirect_uri}")
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    logger.info(f"✅ redirect_uri validated")

    # Check if approved
    logger.info(f"📝 Checking approval status: approved={approved}")
    if approved.lower() != "true":
        logger.info(f"❌ User denied access")
        # User denied - redirect with error
        params = {"error": "access_denied", "error_description": "User denied access"}
        if state:
            params["state"] = state

        redirect_url = f"{redirect_uri}?{urlencode(params)}"
        return RedirectResponse(url=redirect_url, status_code=303)

    logger.info(f"✅ User approved access")
    # User approved - create authorization code
    requested_scopes = scopes.split(",") if scopes else ["mcp:execute"]
    logger.info(f"📝 Requested scopes: {requested_scopes}")

    # Get user's first organization
    logger.info(f"📝 Getting user organization...")
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == current_user.id)
        .limit(1)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        logger.error(f"❌ User has no organization")
        raise HTTPException(status_code=400, detail="User has no organization")
    logger.info(f"✅ Organization membership found: org_id={membership.organization_id}")

    # Get organization
    from ...models.organization import Organization
    organization = await db.get(Organization, membership.organization_id)
    logger.info(f"✅ Organization retrieved: {organization.name}")

    # Create authorization code
    logger.info(f"📝 Creating authorization code...")
    auth_code = await oauth_service.create_authorization_code(
        client=client,
        user=current_user,
        organization=organization,
        redirect_uri=redirect_uri,
        scopes=requested_scopes,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method
    )
    logger.info(f"✅ Authorization code created: {auth_code.code[:10]}...")

    # Audit: user consent granted
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.OAUTH_CONSENT_GRANT,
            actor_id=current_user.id,
            organization_id=membership.organization_id,
            resource_type="oauth_client",
            resource_id=str(client.id),
            details={
                "client_id": client_id,
                "client_name": client.name,
                "scopes": requested_scopes,
                "code_challenge_method": code_challenge_method,
            },
            request=request,
        )
    except Exception:
        pass

    # Redirect to client with authorization code
    params = {"code": auth_code.code}
    if state:
        params["state"] = state

    redirect_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/token", response_model=TokenResponse)
async def token_exchange(
    request: Request,
    grant_type: str = Form(...),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    refresh_token: Optional[str] = Form(None),
    client_id: str = Form(...),
    client_secret: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
    resource: Optional[str] = Form(None),  # Claude Desktop sends this
    oauth_service: OAuthService = Depends(get_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth token endpoint (Step 3) - RFC 6749 compliant.

    Client exchanges authorization code for access token.
    Accepts application/x-www-form-urlencoded format (OAuth 2.0 standard).

    Form Parameters:
    - grant_type: "authorization_code"
    - code: Authorization code from step 2
    - redirect_uri: Must match the one used in authorization request
    - client_id: Client identifier
    - client_secret: Client secret (optional for public clients with PKCE)
    - code_verifier: PKCE verifier (required if PKCE was used)
    - resource: Resource indicator (optional, RFC 8707)

    Response:
    ```json
    {
        "access_token": "jwt_token...",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "mcp:execute mcp:read",
        "user_id": "...",
        "organization_id": "..."
    }
    ```
    """
    import logging
    logger = logging.getLogger("oauth")

    logger.info(f"🎫 POST /token called - grant_type: {grant_type}, client_id: {client_id}, code: {code[:10] if code else None}...")

    # Validate grant_type
    if grant_type not in ["authorization_code", "refresh_token"]:
        logger.error(f"❌ Invalid grant_type: {grant_type}")
        raise HTTPException(
            status_code=400,
            detail="Invalid grant_type. Only 'authorization_code' and 'refresh_token' are supported."
        )

    # Handle refresh_token grant type
    if grant_type == "refresh_token":
        logger.info(f"🔄 Processing refresh_token grant...")

        if not refresh_token:
            logger.error(f"❌ refresh_token parameter is required")
            raise HTTPException(
                status_code=400,
                detail="refresh_token parameter is required for refresh_token grant"
            )

        # Decode and validate refresh token
        logger.info(f"📝 Decoding refresh token...")
        payload = auth_service.decode_token(refresh_token)
        if not payload:
            logger.error(f"❌ Invalid or expired refresh token")
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token"
            )

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            logger.error(f"❌ Token is not a refresh token")
            raise HTTPException(
                status_code=401,
                detail="Invalid token type"
            )

        # Get user from refresh token
        user_id = payload.get("sub")
        if not user_id:
            logger.error(f"❌ Invalid token payload - missing user ID")
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload"
            )

        # Get user directly from database using the user_id from token payload
        # Note: We cannot use get_user_from_token() here because it only accepts access tokens
        logger.info(f"📝 Getting user from database: {user_id}")
        from uuid import UUID
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            logger.error(f"❌ Invalid user ID format in refresh token")
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload"
            )

        result = await db.execute(
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.id == user_uuid)
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"❌ User not found: {user_id}")
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        logger.info(f"✅ User found: {user.email}")

        # Get organization (use the org_id from the token or fall back to user's first organization)
        org_id_str = payload.get("org_id")
        if not org_id_str:
            if len(user.organization_memberships) == 1:
                org_id_str = str(user.organization_memberships[0].organization_id)
            elif user.organization_memberships:
                raise HTTPException(
                    status_code=400,
                    detail="Organization context required"
                )
        if not org_id_str:
            logger.error(f"❌ User has no organization")
            raise HTTPException(
                status_code=400,
                detail="User has no organization"
            )

        # Generate new access token
        logger.info(f"📝 Generating new access token...")
        new_access_token, new_access_jti, _ = auth_service.create_access_token(
            user_id=str(user.id),
            organization_id=org_id_str,
            return_jti=True,
        )
        logger.info(f"✅ New access token generated")

        # Generate new refresh token (rotate refresh tokens for security)
        logger.info(f"📝 Generating new refresh token (rotation)...")
        new_refresh_token, new_refresh_jti, _ = auth_service.create_refresh_token(
            user_id=user.id,
            organization_id=org_id_str,
            return_jti=True,
        )
        logger.info(f"✅ New refresh token generated")

        # Bump last_seen_at on existing OAuthSession(s) for this user×client.
        # We don't create a new session row on refresh — the original grant
        # stays the source of truth. If no session exists yet (legacy grant
        # issued before this code shipped), we backfill one so that
        # /connected-apps still surfaces it.
        try:
            from ...models.oauth import OAuthClient
            from ...models.oauth_session import OAuthSession
            client_row_q = await db.execute(
                select(OAuthClient).where(OAuthClient.client_id == client_id)
            )
            client_row = client_row_q.scalar_one_or_none()
            if client_row:
                sess_q = await db.execute(
                    select(OAuthSession)
                    .where(OAuthSession.user_id == user.id)
                    .where(OAuthSession.oauth_client_id == client_row.id)
                    .where(OAuthSession.revoked_at.is_(None))
                    .order_by(OAuthSession.created_at.desc())
                    .limit(1)
                )
                sess = sess_q.scalar_one_or_none()
                from datetime import datetime as _dt
                if sess:
                    sess.last_seen_at = _dt.utcnow()
                    sess.refresh_token_jti = new_refresh_jti
                    sess.access_token_jti = new_access_jti
                else:
                    from uuid import UUID as _UUID
                    backfill = OAuthSession(
                        user_id=user.id,
                        oauth_client_id=client_row.id,
                        organization_id=_UUID(org_id_str) if org_id_str else None,
                        access_token_jti=new_access_jti,
                        refresh_token_jti=new_refresh_jti,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        last_seen_at=_dt.utcnow(),
                    )
                    db.add(backfill)
                await db.commit()
        except Exception as exc:  # pragma: no cover — best-effort tracking
            logger.warning(f"OAuthSession bump failed: {exc}")

        # Return token response with proper expiration from settings
        from ...core.config import settings
        logger.info(f"🎉 Token refresh successful for user: {user.email}")

        # Audit: refresh token grant
        try:
            from ...services.audit_service import AuditService
            from ...models.audit_log import AuditAction
            from uuid import UUID as _UUID
            await AuditService(db).log_action(
                action=AuditAction.OAUTH_TOKEN_REFRESH,
                actor_id=user.id,
                organization_id=_UUID(org_id_str) if org_id_str else None,
                resource_type="oauth_token",
                resource_id=client_id,
                details={"client_id": client_id, "grant_type": "refresh_token"},
                request=request,
            )
        except Exception:
            pass

        return TokenResponse(
            access_token=new_access_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
            refresh_token=new_refresh_token,
            scope="mcp:execute mcp:read mcp:write offline_access",  # Include offline_access
            user_id=user.id,
            organization_id=org_id_str
        )

    # Handle authorization_code grant type (existing logic)
    if not code or not redirect_uri:
        logger.error(f"❌ code and redirect_uri are required for authorization_code grant")
        raise HTTPException(
            status_code=400,
            detail="code and redirect_uri parameters are required for authorization_code grant"
        )

    # Validate client credentials (if client_secret provided)
    client = None
    if client_secret:
        logger.info(f"📝 Validating client credentials for: {client_id}")
        client = await oauth_service.validate_client_credentials(
            client_id,
            client_secret
        )
        if not client:
            logger.error(f"❌ Invalid client credentials for: {client_id}")
            raise HTTPException(
                status_code=401,
                detail="Invalid client credentials"
            )
        logger.info(f"✅ Client credentials validated")
    else:
        # Public client (PKCE required)
        logger.info(f"📝 Public client - getting client by ID: {client_id}")
        client = await oauth_service.get_client_by_id(client_id)
        if not client:
            logger.error(f"❌ Invalid client_id: {client_id}")
            raise HTTPException(status_code=401, detail="Invalid client_id")
        logger.info(f"✅ Client found")

    # Validate and consume authorization code
    logger.info(f"📝 Validating authorization code: {code[:10]}...")
    auth_code = await oauth_service.validate_and_consume_code(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier
    )

    if not auth_code:
        logger.error(f"❌ Invalid or expired authorization code")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired authorization code"
        )
    logger.info(f"✅ Authorization code validated and consumed")

    # Get user
    logger.info(f"📝 Getting user: {auth_code.user_id}")
    user = await db.get(User, auth_code.user_id)
    if not user:
        logger.error(f"❌ User not found: {auth_code.user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    logger.info(f"✅ User found: {user.email}")

    # Generate JWT access token (reuse existing auth service)
    logger.info(f"📝 Generating JWT access token...")
    access_token, access_jti, _ = auth_service.create_access_token(
        user_id=str(user.id),
        organization_id=str(auth_code.organization_id),
        return_jti=True,
    )
    logger.info(f"✅ Access token generated")

    # Generate refresh token for automatic session renewal
    logger.info(f"📝 Generating refresh token...")
    refresh_token, refresh_jti, _ = auth_service.create_refresh_token(
        user_id=user.id,
        organization_id=auth_code.organization_id,
        return_jti=True,
    )
    logger.info(f"✅ Refresh token generated")

    # Story H — record the OAuth grant as a connected-app session row
    # so the user can list and revoke it from the settings page.
    try:
        from ...models.oauth_session import OAuthSession
        from datetime import datetime as _dt
        session_row = OAuthSession(
            user_id=user.id,
            oauth_client_id=client.id if client else auth_code.client_id,
            organization_id=auth_code.organization_id,
            access_token_jti=access_jti,
            refresh_token_jti=refresh_jti,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            last_seen_at=_dt.utcnow(),
        )
        db.add(session_row)
        await db.commit()
    except Exception as exc:  # pragma: no cover — best-effort tracking
        logger.warning(f"OAuthSession insert failed: {exc}")

    # Return token response with proper expiration from settings
    from ...core.config import settings
    # Ensure offline_access is in scopes for refresh token support
    scopes = auth_code.scopes if "offline_access" in auth_code.scopes else auth_code.scopes + ["offline_access"]
    logger.info(f"🎉 Token exchange successful for user: {user.email}")

    # Audit: authorization_code grant
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction
        await AuditService(db).log_action(
            action=AuditAction.OAUTH_TOKEN_GRANT,
            actor_id=user.id,
            organization_id=auth_code.organization_id,
            resource_type="oauth_token",
            resource_id=client_id,
            details={
                "client_id": client_id,
                "grant_type": "authorization_code",
                "scopes": scopes,
                "client_name": client.name if client else None,
            },
            request=request,
        )
    except Exception:
        pass

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        refresh_token=refresh_token,
        scope=" ".join(scopes),
        user_id=user.id,
        organization_id=auth_code.organization_id
    )
