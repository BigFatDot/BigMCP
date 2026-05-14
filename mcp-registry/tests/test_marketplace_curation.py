"""End-to-end tests for org-scoped marketplace curation (Phase 2).

Coverage:
- Empty state: GET returns rules=[] + zero counts.
- Batch upsert creates rows; counts and rules update.
- Setting status=null removes the row (back to default = visible).
- Hidden status survives a round-trip and is the only filter exposed
  in counts; the marketplace API filtering is exercised at the
  service-layer level (see test_curation_filter_in_list_servers).
- Validation: invalid status returns 400 with a helpful detail.
- Endpoint requires instance admin (non-admin → 403).
- Audit trail: a curation change emits an instance.policy_changed log.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.org_marketplace_curation import (
    OrgMarketplaceCuration,
    OrgMarketplaceCurationStatus,
)
from app.models.organization import OrganizationMember
from app.models.user import User


pytestmark = pytest.mark.asyncio


async def _promote(db_session: AsyncSession, email: str) -> None:
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db_session.commit()


async def _resolve_org_id(db_session: AsyncSession, email: str):
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    member = (
        await db_session.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


# ---------------------------------------------------------------------------
# GET — empty state + counts
# ---------------------------------------------------------------------------


async def test_get_empty_state(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    resp = await client.get(
        "/api/v1/admin/org/marketplace-curation", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rules"] == []
    assert body["counts"] == {"approved": 0, "featured": 0, "hidden": 0}


async def test_requires_instance_admin(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    # test_user is auto-promoted (first user). Register a second user
    # WITHOUT instance_admin and verify the endpoint rejects.
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "non-admin-curation@example.com",
            "password": "NotAdmin123!",
            "name": "Non Admin",
        },
    )
    assert register.status_code in (201, 202)

    from sqlalchemy import update
    await db_session.execute(
        update(User)
        .where(User.email == "non-admin-curation@example.com")
        .values(email_verified=True)
    )
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "non-admin-curation@example.com",
            "password": "NotAdmin123!",
        },
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(
        "/api/v1/admin/org/marketplace-curation", headers=headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT — batch upsert
# ---------------------------------------------------------------------------


async def test_batch_upsert_creates_rules_and_updates_counts(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    payload = {
        "items": [
            {"server_id": "github", "status": "featured", "featured_order": 1},
            {"server_id": "notion", "status": "approved"},
            {"server_id": "consumer-toy", "status": "hidden", "notes": "n/a for prod"},
        ]
    }
    resp = await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json=payload,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["counts"] == {"approved": 1, "featured": 1, "hidden": 1}
    rules_by_id = {r["server_id"]: r for r in body["rules"]}
    assert rules_by_id["github"]["status"] == "featured"
    assert rules_by_id["github"]["featured_order"] == 1
    assert rules_by_id["consumer-toy"]["notes"] == "n/a for prod"


async def test_status_null_removes_existing_rule(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])

    # First create a rule
    create = await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={"items": [{"server_id": "to-remove", "status": "hidden"}]},
        headers=auth_headers,
    )
    assert create.json()["counts"]["hidden"] == 1

    # Then remove it via status=null
    remove = await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={"items": [{"server_id": "to-remove", "status": None}]},
        headers=auth_headers,
    )
    assert remove.status_code == 200
    body = remove.json()
    assert body["counts"]["hidden"] == 0
    assert all(r["server_id"] != "to-remove" for r in body["rules"])


async def test_invalid_status_returns_400(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    resp = await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={"items": [{"server_id": "x", "status": "bogus"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "bogus" in resp.text.lower()


async def test_update_changes_persist(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    user_id, org_id = await _resolve_org_id(db_session, test_user["email"])

    await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={"items": [{"server_id": "x", "status": "approved"}]},
        headers=auth_headers,
    )
    # Flip to featured
    await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={
            "items": [
                {
                    "server_id": "x",
                    "status": "featured",
                    "featured_order": 5,
                    "notes": "promoted",
                }
            ]
        },
        headers=auth_headers,
    )

    db_session.expire_all()
    rows = (
        await db_session.execute(
            select(OrgMarketplaceCuration).where(
                OrgMarketplaceCuration.organization_id == org_id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "featured"
    assert rows[0].featured_order == 5
    assert rows[0].notes == "promoted"
    assert rows[0].curated_by_user_id == user_id


async def test_audit_trail_emitted(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    await client.put(
        "/api/v1/admin/org/marketplace-curation",
        json={"items": [{"server_id": "audit-target", "status": "featured"}]},
        headers=auth_headers,
    )
    audits = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.POLICY_CHANGED.value)
            .where(AuditLog.resource_type == "org_marketplace_curation")
        )
    ).scalars().all()
    assert len(audits) >= 1
    last = audits[-1]
    assert last.details["changes_count"] >= 1
    assert any(c["server_id"] == "audit-target" for c in last.details["changes"])


# ---------------------------------------------------------------------------
# Service-layer filter
# ---------------------------------------------------------------------------


async def test_curation_filter_in_list_servers(
    db_session: AsyncSession, test_user: dict
):
    """Service-level: hidden servers disappear from the listing.

    Skipped when the marketplace cache is empty — we don't trigger a
    live npm/GitHub sync in tests (it takes ~2 minutes); the in-memory
    cache is populated only when the gateway boots in the same process.
    """
    user_id, org_id = await _resolve_org_id(db_session, test_user["email"])

    from app.services.marketplace_service import (
        MarketplaceSyncService,
        get_marketplace_service,
    )

    svc: MarketplaceSyncService = get_marketplace_service()
    if not svc._servers:
        pytest.skip(
            "Marketplace cache empty in test env (no live sync in tests)"
        )

    sample_id = next(iter(svc._servers.keys()))

    # Insert a hidden curation row directly (faster than going via API)
    db_session.add(
        OrgMarketplaceCuration(
            organization_id=org_id,
            marketplace_server_id=sample_id,
            status=OrgMarketplaceCurationStatus.HIDDEN.value,
        )
    )
    await db_session.commit()

    result = await svc.list_servers(
        organization_id=org_id, db=db_session, limit=200
    )
    server_ids = [s["id"] for s in result["servers"]]
    assert sample_id not in server_ids
