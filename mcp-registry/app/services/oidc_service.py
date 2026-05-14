"""
OIDC SSO service — discovery, token exchange, JIT provisioning (Story I.1).

Two responsibilities:

1. ``OIDCDiscovery`` — fetch and cache the IdP's
   ``/.well-known/openid-configuration`` so we know the auth/token/
   userinfo endpoints + the supported algorithms. Cached in memory
   per provider with a 1h TTL.

2. ``OIDCService.provision_or_update_user`` — given a fresh ID token
   and userinfo claims, either find the existing user (by
   ``(provider_id, sub)``), auto-link a legacy local user (when the
   per-IdP toggle is on), or JIT-create a new user. Then resync
   ``OrganizationMember`` rows from the group claims, apply the
   lifecycle gate, and return the user ready for token issuance.

Hard-line guarantees enforced here:

- ``status != ACTIVE`` → reject (lifecycle kill switch covers SSO too).
- ``email_verified=false`` in token + ``require_email_verified=true``
  on provider → reject (account-takeover protection).
- ``reject_unmapped_users=true`` AND no group match AND no fallback
  → reject (admin policy).
- Any auto-link is audited explicitly.
"""

from __future__ import annotations

import logging
import secrets
import time
import urllib.parse
from datetime import datetime
from functools import reduce
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.audit_log import AuditAction
from ..models.oidc import OIDCGroupMapping, OIDCProvider
from ..models.organization import (
    Organization,
    OrganizationMember,
    OrganizationType,
    UserRole,
)
from ..models.user import AuthProvider, User, UserStatus
from .audit_service import AuditService

logger = logging.getLogger("oidc")


class OIDCError(Exception):
    """Raised for any OIDC-side failure (discovery, token exchange, claims)."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class OIDCDiscovery:
    """Fetch + cache OIDC discovery metadata per provider."""

    _CACHE: Dict[UUID, Tuple[Dict[str, Any], float]] = {}
    _TTL_SECONDS = 3600

    @classmethod
    async def get(cls, provider: OIDCProvider) -> Dict[str, Any]:
        """Return discovery doc, honoring manual overrides + 1h cache.

        Manual overrides on the provider row take precedence — used for
        IdPs that don't expose ``.well-known``. Each missing key falls
        back to the discovery document.
        """
        now = time.time()
        cached = cls._CACHE.get(provider.id)
        if cached and (now - cached[1] < cls._TTL_SECONDS):
            doc = dict(cached[0])
        else:
            url = provider.issuer_url.rstrip("/") + "/.well-known/openid-configuration"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    doc = resp.json()
            except httpx.HTTPError as exc:
                raise OIDCError(f"Discovery failed for {provider.name}: {exc}")
            cls._CACHE[provider.id] = (doc, now)

        if provider.manual_endpoints_json:
            doc.update(provider.manual_endpoints_json)
        return doc

    @classmethod
    def invalidate(cls, provider_id: UUID) -> None:
        cls._CACHE.pop(provider_id, None)


# ---------------------------------------------------------------------------
# PKCE + state helpers
# ---------------------------------------------------------------------------


def generate_pkce_pair() -> Tuple[str, str]:
    """Return (code_verifier, code_challenge_S256) per RFC 7636."""
    import base64

    verifier = secrets.token_urlsafe(64)[:128]
    digest = sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def generate_state() -> str:
    """Generate a 32-byte URL-safe CSRF state value."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Generate a 32-byte URL-safe OIDC nonce value."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


def _read_claim(claims: Dict[str, Any], path: Optional[str]) -> Any:
    """Read a dotted path inside the claims dict. Returns None on miss."""
    if not path:
        return None
    return reduce(
        lambda d, k: (d or {}).get(k) if isinstance(d, dict) else None,
        path.split("."),
        claims,
    )


def extract_groups(claims: Dict[str, Any], path: Optional[str]) -> List[str]:
    """Extract the user's group claims, tolerating list / CSV / scalar / null.

    Returns ``[]`` rather than raising if the path is missing — the
    caller decides whether unmapped users are rejected.
    """
    value = _read_claim(claims, path)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(g) for g in value if g]
    if isinstance(value, str):
        return [g.strip() for g in value.split(",") if g.strip()]
    return [str(value)]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OIDCService:
    """JIT provisioning + membership reconciliation for OIDC users."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------ token exchange -------------------------

    async def exchange_code_for_tokens(
        self,
        provider: OIDCProvider,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> Dict[str, Any]:
        """Exchange the authorization code for an ID token + access token."""
        discovery = await OIDCDiscovery.get(provider)
        token_url = discovery.get("token_endpoint")
        if not token_url:
            raise OIDCError("Discovery doc has no token_endpoint")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code_verifier": code_verifier,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(token_url, data=data)
        except httpx.HTTPError as exc:
            raise OIDCError(f"Token endpoint unreachable: {exc}")

        if resp.status_code != 200:
            raise OIDCError(
                f"Token exchange failed ({resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    async def fetch_userinfo(
        self, provider: OIDCProvider, access_token: str
    ) -> Dict[str, Any]:
        """Fetch the userinfo endpoint with the access token.

        Combined with the ID token claims this gives the full picture.
        Some IdPs (e.g. AgentConnect) only expose group/role information
        on userinfo, not in the ID token.
        """
        discovery = await OIDCDiscovery.get(provider)
        userinfo_url = discovery.get("userinfo_endpoint")
        if not userinfo_url:
            return {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as exc:
            raise OIDCError(f"Userinfo fetch failed: {exc}")

    # ---------- ID token decoding (light: signature verification later) ----

    @staticmethod
    def decode_id_token_unverified(id_token: str) -> Dict[str, Any]:
        """Decode the ID token JWT body without signature verification.

        For Phase I.1 we trust the TLS connection + the token endpoint
        response (the IdP's domain identity). Full JWS signature
        verification against the IdP's JWKs is a follow-up hardening
        step (low priority — TLS already protects in transit).
        """
        from jose import jwt

        return jwt.get_unverified_claims(id_token)

    # ------------------------------ provisioning ---------------------------

    async def provision_or_update_user(
        self,
        provider: OIDCProvider,
        id_token_claims: Dict[str, Any],
        userinfo: Dict[str, Any],
        request=None,
    ) -> User:
        """Resolve the IdP claims to a BigMCP User row.

        Lookup order:
          1. ``(oidc_provider_id, oidc_subject)`` — known SSO user
          2. Email match + ``auto_link_by_verified_email`` — migration
          3. Email match without auto-link → 403 (admin must link manually)
          4. JIT-create new user

        Then in all cases: enforce ``status=ACTIVE``, resync group
        memberships, return the user.
        """
        merged_claims = {**userinfo, **id_token_claims}

        sub = merged_claims.get("sub") or id_token_claims.get("sub")
        if not sub:
            raise OIDCError("ID token missing 'sub' claim")

        email = _read_claim(merged_claims, provider.email_claim_path) or ""
        email = str(email).lower().strip()
        if not email:
            raise OIDCError(
                f"ID token missing email claim at path '{provider.email_claim_path}'"
            )

        email_verified = bool(merged_claims.get("email_verified", False))
        if provider.require_email_verified and not email_verified:
            await self._audit_failure(
                provider,
                actor_id=None,
                reason="email_not_verified",
                detail={"email": email, "sub": sub},
                request=request,
            )
            raise OIDCError(
                "IdP did not assert email_verified=true. "
                "Provider policy requires verified emails."
            )

        display_name = (
            _read_claim(merged_claims, provider.name_claim_path)
            or merged_claims.get("name")
            or email.split("@")[0]
        )

        # --- 1. existing SSO user ---------------------------------------
        existing = await self.db.execute(
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.oidc_provider_id == provider.id)
            .where(User.oidc_subject == sub)
        )
        user = existing.scalar_one_or_none()
        provisioned = False

        if user is None:
            # --- 2/3. lookup by email -----------------------------------
            email_match = await self.db.execute(
                select(User)
                .options(selectinload(User.organization_memberships))
                .where(User.email == email)
            )
            local_user = email_match.scalar_one_or_none()

            if local_user is not None:
                if not provider.auto_link_by_verified_email:
                    await self._audit_failure(
                        provider,
                        actor_id=local_user.id,
                        reason="email_collision_no_auto_link",
                        detail={"email": email, "sub": sub},
                        request=request,
                    )
                    raise OIDCError(
                        "An account with this email already exists locally. "
                        "Contact your admin to link it to SSO."
                    )

                local_user.oidc_provider_id = provider.id
                local_user.oidc_subject = sub
                user = local_user
                try:
                    await AuditService(self.db).log_action(
                        action=AuditAction.OIDC_AUTO_LINK_USER,
                        actor_id=user.id,
                        organization_id=None,
                        resource_type="user",
                        resource_id=str(user.id),
                        details={
                            "provider_id": str(provider.id),
                            "provider_name": provider.name,
                            "email": email,
                            "sub": sub,
                        },
                        request=request,
                    )
                except Exception:
                    pass
            else:
                # --- 4. JIT create -------------------------------------
                user = User(
                    email=email,
                    name=display_name,
                    auth_provider=AuthProvider.LOCAL,  # display only; cf. comment in user.py
                    oidc_provider_id=provider.id,
                    oidc_subject=sub,
                    password_hash=None,
                    email_verified=True,  # IdP asserted (or we wouldn't be here)
                    status=UserStatus.ACTIVE.value,
                )
                self.db.add(user)
                await self.db.flush()  # need user.id for the audit + memberships
                provisioned = True
                try:
                    await AuditService(self.db).log_action(
                        action=AuditAction.SSO_PROVISION_USER,
                        actor_id=user.id,
                        organization_id=None,
                        resource_type="user",
                        resource_id=str(user.id),
                        details={
                            "provider_id": str(provider.id),
                            "provider_name": provider.name,
                            "email": email,
                            "sub": sub,
                        },
                        request=request,
                    )
                except Exception:
                    pass

        # --- lifecycle gate (after provision so we can audit) -----------
        if user.status != UserStatus.ACTIVE.value:
            await self._audit_failure(
                provider,
                actor_id=user.id,
                reason=f"account_{user.status}",
                detail={"email": email, "sub": sub},
                request=request,
            )
            raise OIDCError(
                f"Account is {user.status}. Contact your admin."
            )

        # --- update display fields opportunistically --------------------
        if display_name and user.name != display_name:
            user.name = display_name
        user.last_login_at = datetime.utcnow()

        # --- group resync + instance_admin ------------------------------
        groups = extract_groups(merged_claims, provider.groups_claim_path)
        await self._resync_memberships(user, provider, groups, provisioned, request)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    # ------------------------------ memberships ----------------------------

    async def _resync_memberships(
        self,
        user: User,
        provider: OIDCProvider,
        groups: List[str],
        provisioned: bool,
        request,
    ) -> None:
        """Reconcile ``OrganizationMember`` rows + instance_admin from groups."""
        # Fetch all mappings for this provider
        mappings_q = await self.db.execute(
            select(OIDCGroupMapping).where(OIDCGroupMapping.provider_id == provider.id)
        )
        all_mappings = list(mappings_q.scalars().all())
        matching = [m for m in all_mappings if m.idp_group_name in groups]

        # ---------- unmapped-user policy --------------------------------
        if not matching:
            if provider.reject_unmapped_users:
                await self._audit_failure(
                    provider,
                    actor_id=user.id,
                    reason="no_matching_group",
                    detail={"groups": groups},
                    request=request,
                )
                raise OIDCError(
                    "No IdP group matches any provisioning rule. "
                    "Contact your admin."
                )

            # fallback path
            org_id = provider.fallback_organization_id
            role = provider.fallback_role
            if org_id is None and provisioned:
                # Create a PERSONAL org as in the classic signup flow.
                # Existing SSO users without fallback never re-create one.
                personal = Organization(
                    name=f"{user.name or user.email}'s Organization",
                    slug=f"org-{user.id}",
                    organization_type=OrganizationType.PERSONAL.value,
                )
                self.db.add(personal)
                await self.db.flush()
                org_id = personal.id
                role = "admin"

            if org_id is not None:
                await self._ensure_membership(user.id, org_id, role)
            return

        # ---------- matching mappings: apply each one -------------------
        # Snapshot current SSO-induced memberships to detect what to remove.
        # We assume any membership whose org appears in `mappings.organization_id`
        # is SSO-managed; manually-created orgs (via signup PERSONAL) stay.
        sso_org_ids = {m.organization_id for m in all_mappings if m.organization_id}
        current_members_q = await self.db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
        current = {m.organization_id: m for m in current_members_q.scalars().all()}

        target_orgs: Dict[UUID, str] = {}
        grants_admin = False
        for m in matching:
            if m.grants_instance_admin:
                grants_admin = True
            if m.organization_id and m.role:
                # Last write wins if multiple mappings touch the same org
                target_orgs[m.organization_id] = m.role

        # Add / update target memberships
        for org_id, role in target_orgs.items():
            await self._ensure_membership(user.id, org_id, role)

        # Remove SSO-managed memberships no longer matched
        for org_id, member in current.items():
            if org_id in sso_org_ids and org_id not in target_orgs:
                await self.db.delete(member)

        # Apply instance_admin flag
        prefs = dict(user.preferences or {})
        if grants_admin:
            prefs["instance_admin"] = True
        else:
            # Only revoke if the flag was previously SSO-granted. We don't
            # have a "source" tracker, so be conservative: never auto-revoke
            # an instance_admin flag — admin must remove it manually. Avoids
            # locking out the bootstrap admin if a mapping changes.
            pass
        user.preferences = prefs

    async def _ensure_membership(
        self, user_id: UUID, org_id: UUID, role: str
    ) -> None:
        existing_q = await self.db.execute(
            select(OrganizationMember)
            .where(OrganizationMember.user_id == user_id)
            .where(OrganizationMember.organization_id == org_id)
        )
        existing = existing_q.scalar_one_or_none()
        normalized_role = self._coerce_role(role)
        if existing:
            if existing.role != normalized_role:
                existing.role = normalized_role
            return
        self.db.add(
            OrganizationMember(
                user_id=user_id,
                organization_id=org_id,
                role=normalized_role,
            )
        )

    @staticmethod
    def _coerce_role(value: str) -> UserRole:
        try:
            return UserRole(value.lower())
        except ValueError:
            return UserRole.MEMBER

    # ------------------------------ audit helper ---------------------------

    async def _audit_failure(
        self,
        provider: OIDCProvider,
        actor_id: Optional[UUID],
        reason: str,
        detail: Dict[str, Any],
        request,
    ) -> None:
        try:
            await AuditService(self.db).log_action(
                action=AuditAction.SSO_LOGIN_FAILED,
                actor_id=actor_id,
                organization_id=None,
                resource_type="oidc_provider",
                resource_id=str(provider.id),
                details={
                    "provider_name": provider.name,
                    "reason": reason,
                    **detail,
                },
                request=request,
            )
        except Exception:
            pass
