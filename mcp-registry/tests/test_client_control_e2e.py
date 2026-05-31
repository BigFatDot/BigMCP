"""End-to-end tests for the N2.2 client-control story.

These exercise the real HTTP surface (FastAPI test client) against the
real DB-backed PolicyResolver, OAuth admin endpoints, and DCR flow.
The CIMD path is the only thing mocked: ``httpx.AsyncClient.get`` is
patched on ``CIMDService`` so we don't make outbound calls to fake
URLs from the test container.

Coverage:
- DCR + admin_approval policy yields ``approval_status=pending``
- Admin approve flips status to ``approved``; admin reject to
  ``rejected``
- ``GET /oauth/authorize`` returns 403 for both ``pending`` and
  ``rejected`` clients (the gate added to N2.2 step 3)
- ``require_cimd`` policy rejects DCR without
  ``client_id_metadata_document``
- A valid CIMD on the trusted list is auto-approved; same CIMD
  off-list lands as pending
- An invalid CIMD URL produces a 400 + ``OAUTH_CIMD_FETCH_FAILED``
  audit entry
- Admin revoke flips ``is_active`` to False
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.instance_settings import InstanceSettings
from app.models.oauth import OAuthClient
from app.models.user import User


CIMD_URL = "https://claude.ai/.well-known/cimd"
GOOD_CIMD_DOC: dict[str, Any] = {
    "client_id": CIMD_URL,
    "client_name": "Claude Desktop (CIMD)",
    "redirect_uris": ["https://claude.ai/api/oauth/callback"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _promote(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db.commit()


async def _put_policy(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {
        "enabled": True,
        "dcr_policy": "open",
        "require_cimd": False,
        "trusted_cimd_urls": [],
        "allowed_redirect_domains": [],
        "auto_approve_cimd": True,
        "notify_admins_on_new_client": True,
    }
    payload.update(overrides)
    resp = await client.put("/api/v1/admin/client-policy", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _patched_cimd(returning: dict | Exception):
    """Patch CIMDService.fetch to return a fixed doc or raise."""

    async def _fake_fetch(self, url: str):  # noqa: ANN001
        if isinstance(returning, Exception):
            raise returning
        return returning

    return patch("app.services.cimd_service.CIMDService.fetch", _fake_fetch)


# ---------------------------------------------------------------------------
# Fixtures: instance singleton + admin caller
# ---------------------------------------------------------------------------


@pytest.fixture
async def seed_instance_settings(db_session: AsyncSession):
    """Make sure the singleton row exists for tests that read policy."""
    existing = await db_session.get(InstanceSettings, 1)
    if existing is None:
        db_session.add(InstanceSettings(id=1, client_control={}))
        await db_session.commit()
    yield


# ---------------------------------------------------------------------------
# Approval flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_approval_policy_dcr_yields_pending(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers, dcr_policy="admin_approval")

    dcr = await client.post(
        "/api/v1/oauth/register",
        json={
            "redirect_uris": ["https://test-client.example/cb"],
            "client_name": "Test pending",
        },
    )
    assert dcr.status_code == 201, dcr.text
    body = dcr.json()
    client_id_str = body["client_id"]

    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == client_id_str)
        )
    ).scalar_one()
    assert row.approval_status == "pending"
    assert row.registration_method == "dcr_approved"


@pytest.mark.asyncio
async def test_admin_approve_then_reject_flow(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers, dcr_policy="admin_approval")

    dcr = await client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://x.example/cb"], "client_name": "x"},
    )
    assert dcr.status_code == 201
    cid = dcr.json()["client_id"]
    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == cid)
        )
    ).scalar_one()

    # Approve
    approve = await client.post(
        f"/api/v1/admin/oauth-clients/{row.id}/approve",
        json={"reason": "vetted"},
        headers=auth_headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["approval_status"] == "approved"

    # Reject moves it back
    reject = await client.post(
        f"/api/v1/admin/oauth-clients/{row.id}/reject",
        json={"reason": "second thoughts"},
        headers=auth_headers,
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["approval_status"] == "rejected"


# ---------------------------------------------------------------------------
# /authorize gate (N2.2 step 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_blocked_for_pending_and_rejected(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers, dcr_policy="admin_approval")

    # Register a client → pending
    dcr = await client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://gated.example/cb"], "client_name": "g"},
    )
    cid = dcr.json()["client_id"]

    # /authorize must refuse with 403 because approval_status=pending.
    # state + PKCE are now mandatory (see oauth security hardening), so
    # we supply valid dummy values to reach the approval gate.
    _pkce_params = {
        "state": "csrf-state-token",
        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        "code_challenge_method": "S256",
    }
    auth_resp = await client.get(
        "/api/v1/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://gated.example/cb",
            "scope": "mcp:execute",
            **_pkce_params,
        },
    )
    assert auth_resp.status_code == 403
    assert "awaiting admin approval" in auth_resp.text.lower()

    # Reject → still 403 with a different message
    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == cid)
        )
    ).scalar_one()
    await client.post(
        f"/api/v1/admin/oauth-clients/{row.id}/reject",
        json={},
        headers=auth_headers,
    )
    auth_resp2 = await client.get(
        "/api/v1/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://gated.example/cb",
            "scope": "mcp:execute",
            **_pkce_params,
        },
    )
    assert auth_resp2.status_code == 403
    assert "rejected" in auth_resp2.text.lower()


# ---------------------------------------------------------------------------
# CIMD policy gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_cimd_rejects_dcr_without_cimd(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers, require_cimd=True)

    dcr = await client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://x.example/cb"], "client_name": "x"},
    )
    assert dcr.status_code == 403
    assert "Client ID Metadata Document" in dcr.text


@pytest.mark.asyncio
async def test_trusted_cimd_dcr_is_auto_approved(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(
        client,
        auth_headers,
        require_cimd=True,
        trusted_cimd_urls=[CIMD_URL],
    )

    with _patched_cimd(GOOD_CIMD_DOC):
        dcr = await client.post(
            "/api/v1/oauth/register",
            json={
                "redirect_uris": ["https://will-be-overridden.example/cb"],
                "client_name": "will be overridden",
                "client_id_metadata_document": CIMD_URL,
            },
        )

    assert dcr.status_code == 201, dcr.text
    body = dcr.json()
    cid = body["client_id"]

    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == cid)
        )
    ).scalar_one()
    assert row.registration_method == "cimd"
    assert row.approval_status == "auto_approved"
    assert row.cimd_url == CIMD_URL
    # CIMD doc wins for client_name + redirect_uris
    assert row.name == GOOD_CIMD_DOC["client_name"]
    assert row.redirect_uris == GOOD_CIMD_DOC["redirect_uris"]


@pytest.mark.asyncio
async def test_untrusted_cimd_dcr_is_pending(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(
        client,
        auth_headers,
        require_cimd=True,
        trusted_cimd_urls=["https://something-else.example/cimd"],
    )

    with _patched_cimd(GOOD_CIMD_DOC):
        dcr = await client.post(
            "/api/v1/oauth/register",
            json={
                "redirect_uris": ["https://x.example/cb"],
                "client_name": "x",
                "client_id_metadata_document": CIMD_URL,
            },
        )

    assert dcr.status_code == 201, dcr.text
    cid = dcr.json()["client_id"]
    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == cid)
        )
    ).scalar_one()
    assert row.registration_method == "cimd"
    assert row.approval_status == "pending"


@pytest.mark.asyncio
async def test_invalid_cimd_returns_400_and_audits_failure(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    from app.services.cimd_service import CIMDFetchError

    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers)

    with _patched_cimd(CIMDFetchError("HTTP 404")):
        dcr = await client.post(
            "/api/v1/oauth/register",
            json={
                "redirect_uris": ["https://x.example/cb"],
                "client_name": "x",
                "client_id_metadata_document": "https://bogus.example/cimd",
            },
        )
    assert dcr.status_code == 400
    assert "Invalid CIMD" in dcr.text

    # Audit row written
    audit_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == AuditAction.OAUTH_CIMD_FETCH_FAILED.value
            )
        )
    ).scalars().all()
    assert len(audit_rows) >= 1


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_revoke_sets_is_active_false(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
    seed_instance_settings,
):
    await _promote(db_session, test_user["email"])
    await _put_policy(client, auth_headers)  # open + auto_approved

    dcr = await client.post(
        "/api/v1/oauth/register",
        json={"redirect_uris": ["https://x.example/cb"], "client_name": "x"},
    )
    cid = dcr.json()["client_id"]
    row = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.client_id == cid)
        )
    ).scalar_one()
    assert row.is_active is True

    row_id = row.id  # capture before expire (lazy-load is not allowed async)
    revoke = await client.delete(
        f"/api/v1/admin/oauth-clients/{row_id}",
        headers=auth_headers,
    )
    assert revoke.status_code == 204

    db_session.expire_all()
    after = (
        await db_session.execute(
            select(OAuthClient).where(OAuthClient.id == row_id)
        )
    ).scalar_one()
    assert after.is_active is False


# ---------------------------------------------------------------------------
# OAuth security hardening: mandatory state + PKCE (S256) on /authorize
# ---------------------------------------------------------------------------


async def _seed_authorize_ready_client(
    client: AsyncClient,
) -> str:
    """Register a DCR client that is immediately authorize-ready."""
    dcr = await client.post(
        "/api/v1/oauth/register",
        json={
            "redirect_uris": ["https://sec.example/cb"],
            "client_name": "sec",
        },
    )
    assert dcr.status_code == 201, dcr.text
    return dcr.json()["client_id"]


@pytest.mark.asyncio
async def test_authorize_rejects_missing_state(
    client: AsyncClient,
    seed_instance_settings,
):
    """RFC 6749 §10.12 — ``state`` is mandatory (CSRF protection)."""
    cid = await _seed_authorize_ready_client(client)
    resp = await client.get(
        "/api/v1/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://sec.example/cb",
            "scope": "mcp:execute",
            # state omitted on purpose
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert "state" in body["error_description"].lower()


@pytest.mark.asyncio
async def test_authorize_rejects_missing_code_challenge(
    client: AsyncClient,
    seed_instance_settings,
):
    """RFC 7636 — PKCE ``code_challenge`` is mandatory."""
    cid = await _seed_authorize_ready_client(client)
    resp = await client.get(
        "/api/v1/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://sec.example/cb",
            "scope": "mcp:execute",
            "state": "csrf-state-token",
            # code_challenge omitted on purpose
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert "code_challenge" in body["error_description"].lower()


@pytest.mark.asyncio
async def test_authorize_rejects_plain_code_challenge_method(
    client: AsyncClient,
    seed_instance_settings,
):
    """Only the ``S256`` challenge method is accepted."""
    cid = await _seed_authorize_ready_client(client)
    resp = await client.get(
        "/api/v1/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": "https://sec.example/cb",
            "scope": "mcp:execute",
            "state": "csrf-state-token",
            "code_challenge": "an-unhashed-verifier",
            "code_challenge_method": "plain",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "invalid_request"
    assert "s256" in body["error_description"].lower()
