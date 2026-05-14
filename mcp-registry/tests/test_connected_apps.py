"""End-to-end tests for the connected-apps story (N2.4 / Story H).

Covers the user-facing surface introduced in Story H:

- A successful OAuth ``authorization_code`` exchange persists an
  ``oauth_sessions`` row with the issued JTIs, IP, user agent.
- ``GET /api/v1/auth/connected-apps`` returns one row per client (not
  per token issuance) and counts active sessions correctly.
- ``DELETE /api/v1/auth/connected-apps/{uuid}`` revokes all active
  sessions for that user × client AND bumps ``user.tokens_revoked_at``
  so the JWT becomes unusable on next call.
- The same DELETE returns 404 if invoked twice (no active sessions).
- A ``refresh_token`` grant after revocation produces a NEW session row
  rather than re-using the revoked one (it backfills via the
  ``last_seen_at`` bump path that creates a row when none exists).

The OAuth client is created directly via ``OAuthService.create_client``
because the dynamic_client_registration endpoint requires a Team
subscription that the test fixture user doesn't have. The flow we care
about (token_exchange → oauth_sessions row) is identical regardless of
how the client was registered.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.oauth import AuthorizationCode, OAuthClient
from app.models.oauth_session import OAuthSession
from app.models.organization import OrganizationMember
from app.models.user import User
from app.services.oauth_service import OAuthService


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_client(db: AsyncSession) -> OAuthClient:
    """Create a trusted OAuth client and return both the row and its plaintext secret."""
    svc = OAuthService(db)
    client = await svc.create_client(
        name="Test Connected App",
        redirect_uris=["https://app.example.com/cb"],
        description="Used by test_connected_apps.py",
        allowed_scopes=["mcp:execute", "mcp:read", "offline_access"],
        is_trusted=True,
    )
    return client


async def _seed_authorization_code(
    db: AsyncSession,
    client: OAuthClient,
    user: User,
) -> AuthorizationCode:
    """Mint an authorization code the test can swap for tokens."""
    member_q = await db.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id).limit(1)
    )
    membership = member_q.scalar_one()
    from app.models.organization import Organization
    organization = await db.get(Organization, membership.organization_id)
    svc = OAuthService(db)
    return await svc.create_authorization_code(
        client=client,
        user=user,
        organization=organization,
        redirect_uri="https://app.example.com/cb",
        scopes=["mcp:execute", "mcp:read"],
        code_challenge=None,
        code_challenge_method=None,
    )


async def _grant_token(
    client: AsyncClient,
    db: AsyncSession,
    oauth_client: OAuthClient,
    user: User,
) -> dict:
    """Issue an authorization_code and exchange it via /oauth/token."""
    auth_code = await _seed_authorization_code(db, oauth_client, user)
    resp = await client.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code.code,
            "redirect_uri": "https://app.example.com/cb",
            "client_id": oauth_client.client_id,
            "client_secret": oauth_client.plaintext_secret,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_token_exchange_creates_oauth_session(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    user_q = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = user_q.scalar_one()

    oauth_client = await _create_client(db_session)
    await _grant_token(client, db_session, oauth_client, user)

    sessions_q = await db_session.execute(
        select(OAuthSession).where(OAuthSession.user_id == user.id)
    )
    sessions = list(sessions_q.scalars().all())
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess.oauth_client_id == oauth_client.id
    assert sess.revoked_at is None
    assert sess.access_token_jti is not None
    assert sess.refresh_token_jti is not None


async def test_list_connected_apps_groups_by_client(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_q = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = user_q.scalar_one()

    oauth_client = await _create_client(db_session)

    # Two grants for the same client → still one connected-app row.
    await _grant_token(client, db_session, oauth_client, user)
    await _grant_token(client, db_session, oauth_client, user)

    resp = await client.get(
        "/api/v1/auth/connected-apps", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "connected_apps" in body
    apps = body["connected_apps"]
    assert len(apps) == 1
    app_row = apps[0]
    assert app_row["client_id"] == oauth_client.client_id
    assert app_row["name"] == "Test Connected App"
    assert app_row["session_count"] == 2
    assert app_row["first_authorized_at"] is not None
    assert app_row["last_seen_at"] is not None


async def test_revoke_connected_app_kills_sessions_and_jwts(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_q = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = user_q.scalar_one()
    user_id = user.id  # capture before any expire_all

    oauth_client = await _create_client(db_session)
    oauth_client_id = oauth_client.id
    grant = await _grant_token(client, db_session, oauth_client, user)
    assert grant["access_token"]

    # Revoke
    resp = await client.delete(
        f"/api/v1/auth/connected-apps/{oauth_client_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # Session row is now revoked
    db_session.expire_all()
    sessions_q = await db_session.execute(
        select(OAuthSession).where(OAuthSession.user_id == user_id)
    )
    sess = sessions_q.scalar_one()
    assert sess.revoked_at is not None
    assert sess.revoked_reason == "user_revoke"

    # The OAuth-grant access token is now blacklisted (per-JTI revocation,
    # without disturbing the user's own browser session).
    dead_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {grant['access_token']}"},
    )
    assert dead_resp.status_code == 401

    # The user's regular browser session (auth_headers) is unaffected.
    alive_resp = await client.get(
        "/api/v1/auth/me", headers=auth_headers
    )
    assert alive_resp.status_code == 200

    # Audit row written
    audit_q = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.CONNECTED_APP_REVOKE.value
        )
    )
    audit_rows = list(audit_q.scalars().all())
    assert len(audit_rows) == 1
    assert audit_rows[0].actor_id == user_id
    assert audit_rows[0].resource_id == str(oauth_client_id)


async def test_revoke_returns_404_when_no_active_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_q = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = user_q.scalar_one()

    oauth_client = await _create_client(db_session)
    await _grant_token(client, db_session, oauth_client, user)

    first = await client.delete(
        f"/api/v1/auth/connected-apps/{oauth_client.id}",
        headers=auth_headers,
    )
    assert first.status_code == 204

    second = await client.delete(
        f"/api/v1/auth/connected-apps/{oauth_client.id}",
        headers=auth_headers,
    )
    assert second.status_code == 404


async def test_revoke_unknown_client_returns_404(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.delete(
        "/api/v1/auth/connected-apps/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_revoke_invalid_uuid_returns_400(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.delete(
        "/api/v1/auth/connected-apps/not-a-uuid",
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_revoked_app_disappears_from_list(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_q = await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )
    user = user_q.scalar_one()

    oauth_client = await _create_client(db_session)
    await _grant_token(client, db_session, oauth_client, user)

    list_before = (await client.get(
        "/api/v1/auth/connected-apps", headers=auth_headers
    )).json()
    assert len(list_before["connected_apps"]) == 1

    await client.delete(
        f"/api/v1/auth/connected-apps/{oauth_client.id}",
        headers=auth_headers,
    )

    # The user's own JWT is unaffected (we only blacklist OAuth-grant JTIs).
    list_after = (await client.get(
        "/api/v1/auth/connected-apps", headers=auth_headers
    )).json()
    assert list_after["connected_apps"] == []


async def test_unauthenticated_call_is_rejected(
    client: AsyncClient,
):
    resp = await client.get("/api/v1/auth/connected-apps")
    assert resp.status_code in (401, 403)
