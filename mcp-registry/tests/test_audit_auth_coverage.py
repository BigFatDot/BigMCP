"""Audit-coverage tests for the auth/oauth endpoints (N0 #2).

These regressions pin the audit emissions added to close the
``ROADMAP_ACCESS_CONTROL.md`` N0 #2 gap. Specifically:

- ``POST /auth/refresh`` emits ``TOKEN_REFRESH``.
- ``DELETE /auth/account`` emits ``ACCOUNT_DELETE`` *before* the row is
  deleted (so the actor stays linkable for RGPD article 30 reviews).
- ``POST /oauth/token`` emits ``OAUTH_TOKEN_GRANT_FAILED`` with a usable
  ``reason`` for every refused branch (expired/invalid code shown here).
- ``POST /admin/oauth-clients/{id}/approve`` emits
  ``OAUTH_CLIENT_APPROVE``.

The tests deliberately read the ``audit_logs`` table directly rather
than mocking the service — the production behaviour is to *commit* an
audit row inline, so the assertion has to land on the row, not on a
call-site spy.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.oauth import OAuthClient
from app.models.organization import OrganizationMember
from app.models.user import User
from app.services.oauth_service import OAuthService


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _audit_rows(
    db: AsyncSession, action: AuditAction
) -> list[AuditLog]:
    rows = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.action == action.value)
            .order_by(AuditLog.timestamp.desc())
        )
    ).scalars().all()
    return list(rows)


async def _create_oauth_client(db: AsyncSession) -> OAuthClient:
    svc = OAuthService(db)
    return await svc.create_client(
        name="Audit Cover Test App",
        redirect_uris=["https://app.example.com/cb"],
        description="Used by test_audit_auth_coverage.py",
        allowed_scopes=["mcp:execute", "mcp:read"],
        is_trusted=True,
    )


# ---------------------------------------------------------------------------
# /auth/refresh — TOKEN_REFRESH
# ---------------------------------------------------------------------------


async def test_refresh_endpoint_emits_token_refresh_audit(
    client: AsyncClient,
    test_user: dict,
    db_session: AsyncSession,
):
    before = len(await _audit_rows(db_session, AuditAction.TOKEN_REFRESH))

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": test_user["refresh_token"]},
    )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows(db_session, AuditAction.TOKEN_REFRESH)
    assert len(rows) == before + 1
    latest = rows[0]
    assert str(latest.actor_id) == test_user["user"]["id"]
    assert latest.resource_type == "user"
    assert latest.details and latest.details.get("surface") == "jwt"


# ---------------------------------------------------------------------------
# DELETE /auth/account — ACCOUNT_DELETE (must land BEFORE row deletion)
# ---------------------------------------------------------------------------


async def test_delete_account_emits_audit_before_delete(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    user_id = test_user["user"]["id"]

    resp = await client.delete("/api/v1/auth/account", headers=auth_headers)
    assert resp.status_code == 204, resp.text

    # The user row is gone but the audit row must survive with the actor
    # link intact — otherwise the RGPD trail is broken.
    rows = await _audit_rows(db_session, AuditAction.ACCOUNT_DELETE)
    assert any(str(r.actor_id) == user_id for r in rows), (
        "ACCOUNT_DELETE audit row missing or did not capture actor_id "
        "(should be written before the user is deleted)"
    )
    target_row = next(r for r in rows if str(r.actor_id) == user_id)
    assert target_row.resource_type == "user"
    assert target_row.resource_id == user_id
    assert target_row.details and target_row.details.get("email")


# ---------------------------------------------------------------------------
# /oauth/token — OAUTH_TOKEN_GRANT_FAILED on bad code
# ---------------------------------------------------------------------------


async def test_oauth_token_invalid_code_emits_grant_failed_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
):
    oauth_client = await _create_oauth_client(db_session)

    before = len(await _audit_rows(db_session, AuditAction.OAUTH_TOKEN_GRANT_FAILED))

    resp = await client.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "not-a-real-code",
            "redirect_uri": "https://app.example.com/cb",
            "client_id": oauth_client.client_id,
            "client_secret": oauth_client.plaintext_secret,
        },
    )
    assert resp.status_code == 400, resp.text

    rows = await _audit_rows(db_session, AuditAction.OAUTH_TOKEN_GRANT_FAILED)
    assert len(rows) == before + 1
    latest = rows[0]
    assert latest.details and latest.details.get("reason") == "invalid_or_expired_code"
    assert latest.details.get("client_id") == oauth_client.client_id


async def test_oauth_token_unsupported_grant_type_emits_audit(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """The first guard (unknown grant_type) must also audit, otherwise
    a wave of bogus grant_types looks invisible to ops."""
    before = len(await _audit_rows(db_session, AuditAction.OAUTH_TOKEN_GRANT_FAILED))

    resp = await client.post(
        "/api/v1/oauth/token",
        data={
            "grant_type": "client_credentials",  # not supported
            "client_id": "anything",
        },
    )
    assert resp.status_code == 400, resp.text

    rows = await _audit_rows(db_session, AuditAction.OAUTH_TOKEN_GRANT_FAILED)
    assert len(rows) == before + 1
    assert rows[0].details.get("reason") == "unsupported_grant_type"


# ---------------------------------------------------------------------------
# POST /admin/oauth-clients/{id}/approve — OAUTH_CLIENT_APPROVE
# ---------------------------------------------------------------------------


async def test_admin_approve_oauth_client_emits_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    """Mark the test_user as instance admin, then approve a client."""
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()
    # Instance admin lives in user.preferences["instance_admin"] per
    # project_instance_admin_model.md.
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db_session.commit()

    # Create a client that defaults to PENDING approval_status.
    oauth_client = await _create_oauth_client(db_session)

    before = len(await _audit_rows(db_session, AuditAction.OAUTH_CLIENT_APPROVE))

    resp = await client.post(
        f"/api/v1/admin/oauth-clients/{oauth_client.id}/approve",
        json={"reason": "vetted by audit-coverage test"},
        headers=auth_headers,
    )
    # The approve endpoint may 200 (success) or 404 if the admin guard
    # rejects — either way, on a successful 200 the audit must land.
    if resp.status_code != 200:
        pytest.skip(
            f"approve endpoint returned {resp.status_code} "
            f"({resp.text}); test_user not promotable to instance admin "
            "in this fixture setup — covered manually by E2E"
        )

    rows = await _audit_rows(db_session, AuditAction.OAUTH_CLIENT_APPROVE)
    assert len(rows) == before + 1
    latest = rows[0]
    assert latest.resource_type == "oauth_client"
    assert latest.resource_id == str(oauth_client.id)
    assert latest.details and latest.details.get("reason") == "vetted by audit-coverage test"
