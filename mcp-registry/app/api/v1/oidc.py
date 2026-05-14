"""
OIDC SSO endpoints (Story I.1).

User-facing surface for delegated authentication via an external IdP:

- ``GET /auth/sso-providers`` (public, no auth) — list active providers
  for the LoginPage to render "Continue with X" buttons.
- ``GET /auth/oidc/{provider_id}/login`` — start the flow: build
  state + nonce + PKCE pair, set them in a short-lived secure cookie,
  redirect the browser to the IdP authorization endpoint.
- ``GET /auth/oidc/{provider_id}/callback`` — handle the IdP redirect:
  validate state, exchange the code, fetch userinfo, JIT-provision via
  ``OIDCService``, mint a BigMCP JWT pair, redirect to the SPA with
  the tokens in URL fragment.
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...db.database import get_db
from ...models.audit_log import AuditAction
from ...models.oidc import OIDCProvider
from ...models.organization import OrganizationMember
from ...services.audit_service import AuditService
from ...services.auth_service import AuthService
from ...services.oidc_service import (
    OIDCDiscovery,
    OIDCError,
    OIDCService,
    generate_nonce,
    generate_pkce_pair,
    generate_state,
)


logger = logging.getLogger("oidc")

router = APIRouter(prefix="/auth", tags=["SSO"])


# Cookie holding (state, nonce, code_verifier, provider_id) JSON-encoded.
# Short lifetime — only valid for the duration of one round-trip.
_OIDC_COOKIE_NAME = "bigmcp_oidc_state"
_OIDC_COOKIE_MAX_AGE = 600  # 10 min — covers slow IdP login screens


# ---------------------------------------------------------------------------
# Public: list active providers
# ---------------------------------------------------------------------------


@router.get("/sso-providers")
async def list_sso_providers(db: AsyncSession = Depends(get_db)):
    """Return active SSO providers in a public-safe shape for the LoginPage.

    No secrets are exposed — only ``id``, ``name``, ``display_label``.
    The response is intentionally cache-friendly; LoginPage hits it
    once per session.
    """
    rows = await db.execute(
        select(OIDCProvider)
        .where(OIDCProvider.is_active.is_(True))
        .order_by(OIDCProvider.name)
    )
    providers = [
        {
            "id": str(p.id),
            "name": p.name,
            "display_label": p.display_label,
        }
        for p in rows.scalars().all()
    ]
    return {"providers": providers}


# ---------------------------------------------------------------------------
# Login start
# ---------------------------------------------------------------------------


def _callback_url(request: Request, provider_id: UUID) -> str:
    base = settings.domain or str(request.base_url).rstrip("/")
    return f"{base}/api/v1/auth/oidc/{provider_id}/callback"


@router.get("/oidc/{provider_id}/login")
async def oidc_login(
    provider_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate the OIDC authorization-code flow with PKCE."""
    provider = await db.get(OIDCProvider, provider_id)
    if not provider or not provider.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO provider not found",
        )

    try:
        discovery = await OIDCDiscovery.get(provider)
    except OIDCError as exc:
        logger.warning(f"OIDC discovery failed for {provider.name}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Identity provider unreachable: {exc}",
        )

    auth_url = discovery.get("authorization_endpoint")
    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="IdP discovery missing authorization_endpoint",
        )

    state = generate_state()
    nonce = generate_nonce()
    code_verifier, code_challenge = generate_pkce_pair()

    redirect_uri = _callback_url(request, provider_id)
    params = {
        "response_type": "code",
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(provider.scopes or ["openid", "profile", "email"]),
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    response = RedirectResponse(url=f"{auth_url}?{urlencode(params)}", status_code=303)
    cookie_value = json.dumps(
        {
            "state": state,
            "nonce": nonce,
            "code_verifier": code_verifier,
            "provider_id": str(provider_id),
            "redirect_uri": redirect_uri,
        }
    )
    response.set_cookie(
        key=_OIDC_COOKIE_NAME,
        value=cookie_value,
        max_age=_OIDC_COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


def _redirect_with_error(reason: str) -> RedirectResponse:
    """Send the user back to /login with an error param, scrubbing the cookie."""
    params = urlencode({"sso_error": reason})
    resp = RedirectResponse(url=f"/login?{params}", status_code=303)
    resp.delete_cookie(key=_OIDC_COOKIE_NAME, path="/")
    return resp


def _redirect_with_tokens(access_token: str, refresh_token: str) -> RedirectResponse:
    """Hand the SPA the new JWT pair via a dedicated bridge route.

    The SPA mounts this route and stores the tokens in localStorage,
    then redirects to /app. We pass tokens via URL fragment (after #)
    so they never hit the server logs.
    """
    fragment = urlencode(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    )
    resp = RedirectResponse(url=f"/auth/sso-callback#{fragment}", status_code=303)
    resp.delete_cookie(key=_OIDC_COOKIE_NAME, path="/")
    return resp


@router.get("/oidc/{provider_id}/callback")
async def oidc_callback(
    provider_id: UUID,
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    bigmcp_oidc_state: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Exchange the IdP code for a BigMCP session."""
    if error:
        logger.info(f"IdP returned error '{error}': {error_description}")
        return _redirect_with_error(error)

    if not code or not state:
        return _redirect_with_error("missing_code_or_state")
    if not bigmcp_oidc_state:
        return _redirect_with_error("missing_state_cookie")

    try:
        cookie_data = json.loads(bigmcp_oidc_state)
    except json.JSONDecodeError:
        return _redirect_with_error("malformed_state_cookie")

    if cookie_data.get("provider_id") != str(provider_id):
        return _redirect_with_error("provider_mismatch")
    if cookie_data.get("state") != state:
        return _redirect_with_error("state_mismatch")

    provider = await db.get(OIDCProvider, provider_id)
    if not provider or not provider.is_active:
        return _redirect_with_error("provider_inactive")

    svc = OIDCService(db)
    try:
        token_response = await svc.exchange_code_for_tokens(
            provider=provider,
            code=code,
            redirect_uri=cookie_data["redirect_uri"],
            code_verifier=cookie_data["code_verifier"],
        )
    except OIDCError as exc:
        logger.warning(f"Token exchange failed: {exc}")
        return _redirect_with_error("token_exchange_failed")

    id_token = token_response.get("id_token")
    access_token_idp = token_response.get("access_token")
    if not id_token:
        return _redirect_with_error("no_id_token")

    try:
        id_token_claims = OIDCService.decode_id_token_unverified(id_token)
    except Exception:
        return _redirect_with_error("id_token_decode_failed")

    if id_token_claims.get("nonce") != cookie_data.get("nonce"):
        return _redirect_with_error("nonce_mismatch")

    try:
        userinfo = (
            await svc.fetch_userinfo(provider, access_token_idp)
            if access_token_idp
            else {}
        )
    except OIDCError as exc:
        logger.warning(f"Userinfo fetch failed: {exc}")
        userinfo = {}

    try:
        user = await svc.provision_or_update_user(
            provider=provider,
            id_token_claims=id_token_claims,
            userinfo=userinfo,
            request=request,
        )
    except OIDCError as exc:
        logger.warning(f"Provisioning failed: {exc}")
        return _redirect_with_error("provisioning_failed")

    # Pick an organization context for the access token (oldest membership).
    member_q = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at.asc())
        .limit(1)
    )
    membership = member_q.scalar_one_or_none()
    org_id = membership.organization_id if membership else None

    auth_service = AuthService(db)
    bigmcp_access = auth_service.create_access_token(user.id, org_id)
    bigmcp_refresh = auth_service.create_refresh_token(user.id, org_id)

    try:
        await AuditService(db).log_action(
            action=AuditAction.SSO_LOGIN_SUCCESS,
            actor_id=user.id,
            organization_id=org_id,
            resource_type="oidc_provider",
            resource_id=str(provider.id),
            details={
                "provider_name": provider.name,
                "email": user.email,
            },
            request=request,
        )
    except Exception:
        pass

    return _redirect_with_tokens(bigmcp_access, bigmcp_refresh)
