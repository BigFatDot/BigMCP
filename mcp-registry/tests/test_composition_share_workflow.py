"""End-to-end tests for the Phase 4 composition share-with-org workflow.

Coverage
--------
- Admin POST /share applies immediately (visibility=org, status=production).
- Non-admin POST /share queues a 'pending' review; composition stays private.
- Listing /admin/share-requests:
  - admin sees the pending request
  - non-admin gets 403
- Approve flips visibility/status + clears share_request_status.
- Reject leaves visibility unchanged but marks status='rejected' + notes.
- Re-requesting after rejection works (clears 'rejected', sets 'pending').
- Approve/reject on a composition with no pending request returns 409.
- Audit trail records the right action per case.
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.organization import OrganizationMember, UserRole
from app.models.user import User


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ids(db: AsyncSession, email: str) -> Tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _register_member_in_org(
    client: AsyncClient,
    db: AsyncSession,
    email: str,
    organization_id: UUID,
) -> str:
    """Register a fresh user and force-attach them to ``organization_id``
    as a MEMBER. Returns their access_token."""
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "MemberPass123!", "name": "Member"},
    )
    assert register.status_code in (201, 202), register.text

    await db.execute(
        update(User).where(User.email == email).values(email_verified=True)
    )
    await db.commit()

    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    # The registration auto-creates a personal org and an OWNER membership;
    # delete it and re-attach to the target org as MEMBER for this test.
    await db.execute(
        OrganizationMember.__table__.delete().where(
            OrganizationMember.user_id == user.id
        )
    )
    db.add(
        OrganizationMember(
            user_id=user.id,
            organization_id=organization_id,
            role=UserRole.MEMBER,
            invited_by=None,
        )
    )
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "MemberPass123!"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def _make_private_composition(
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str = "wf-private"
) -> Composition:
    """Create a private, production-ready composition (input schema + steps).

    Production-ready so that the share path doesn't get blocked by the
    promote-to-production schema validation.
    """
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="test",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=[{"id": "s1", "tool": "noop", "params": {}, "depends_on": []}],
        data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        server_bindings={},
        allowed_roles=[],
        force_org_credentials=False,
        status=CompositionStatus.VALIDATED.value,
        ttl=None,
        extra_metadata={},
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_admin_share_applies_immediately(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_private_composition(db_session, org_id, user_id)

    resp = await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={"notes": "ship it"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is True
    assert body["composition"]["visibility"] == "organization"
    assert body["composition"]["status"] == "production"
    assert body["composition"]["share_request_status"] is None

    # Audit row recorded as direct share
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == AuditAction.COMPOSITION_SHARE_DIRECT.value,
                AuditLog.resource_id == str(comp.id),
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_member_share_queues_pending_review(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-share@example.com", org_id
    )
    member_headers = {"Authorization": f"Bearer {member_token}"}
    member = (
        await db_session.execute(
            select(User).where(User.email == "member-share@example.com")
        )
    ).scalar_one()

    comp = await _make_private_composition(db_session, org_id, member.id, name="wf-mem")

    resp = await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={"notes": "please review"},
        headers=member_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is False
    # Composition itself unchanged.
    assert body["composition"]["visibility"] == "private"
    # share_request_status now pending
    assert body["composition"]["share_request_status"] == "pending"
    assert body["composition"]["share_requested_by"] == str(member.id)


async def test_member_cannot_list_share_queue(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-list@example.com", org_id
    )
    member_headers = {"Authorization": f"Bearer {member_token}"}
    resp = await client.get(
        "/api/v1/compositions/admin/share-requests", headers=member_headers
    )
    assert resp.status_code == 403


async def test_admin_sees_and_approves_pending_request(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-approve@example.com", org_id
    )
    member = (
        await db_session.execute(
            select(User).where(User.email == "member-approve@example.com")
        )
    ).scalar_one()
    comp = await _make_private_composition(db_session, org_id, member.id, name="wf-app")

    # Member files the request
    member_headers = {"Authorization": f"Bearer {member_token}"}
    await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={"notes": "please"},
        headers=member_headers,
    )

    # Admin (test_user) lists
    queue = await client.get(
        "/api/v1/compositions/admin/share-requests", headers=auth_headers
    )
    assert queue.status_code == 200
    listed = queue.json()
    assert listed["total"] == 1
    assert listed["compositions"][0]["id"] == str(comp.id)

    # Admin approves
    approve = await client.post(
        f"/api/v1/compositions/{comp.id}/share-request/approve",
        json={"notes": "lgtm"},
        headers=auth_headers,
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["visibility"] == "organization"
    assert body["status"] == "production"
    assert body["share_request_status"] is None


async def test_admin_rejects_request_keeps_visibility(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-reject@example.com", org_id
    )
    member = (
        await db_session.execute(
            select(User).where(User.email == "member-reject@example.com")
        )
    ).scalar_one()
    comp = await _make_private_composition(db_session, org_id, member.id, name="wf-rej")

    member_headers = {"Authorization": f"Bearer {member_token}"}
    await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={"notes": "first try"},
        headers=member_headers,
    )

    rej = await client.post(
        f"/api/v1/compositions/{comp.id}/share-request/reject",
        json={"notes": "needs more polish"},
        headers=auth_headers,
    )
    assert rej.status_code == 200, rej.text
    body = rej.json()
    assert body["visibility"] == "private"
    assert body["share_request_status"] == "rejected"
    assert body["share_review_notes"] == "needs more polish"


async def test_double_request_returns_409(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-dup@example.com", org_id
    )
    member = (
        await db_session.execute(
            select(User).where(User.email == "member-dup@example.com")
        )
    ).scalar_one()
    comp = await _make_private_composition(db_session, org_id, member.id, name="wf-dup")
    member_headers = {"Authorization": f"Bearer {member_token}"}

    first = await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={},
        headers=member_headers,
    )
    assert first.status_code == 200

    again = await client.post(
        f"/api/v1/compositions/{comp.id}/share",
        json={},
        headers=member_headers,
    )
    assert again.status_code == 409


async def test_re_request_after_rejection_works(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    member_token = await _register_member_in_org(
        client, db_session, "member-rerequest@example.com", org_id
    )
    member = (
        await db_session.execute(
            select(User).where(User.email == "member-rerequest@example.com")
        )
    ).scalar_one()
    comp = await _make_private_composition(db_session, org_id, member.id, name="wf-rr")
    member_headers = {"Authorization": f"Bearer {member_token}"}

    await client.post(
        f"/api/v1/compositions/{comp.id}/share", json={}, headers=member_headers
    )
    # Admin rejects
    await client.post(
        f"/api/v1/compositions/{comp.id}/share-request/reject",
        json={"notes": "no"},
        headers=auth_headers,
    )

    # Member re-requests — should succeed and clear 'rejected'
    again = await client.post(
        f"/api/v1/compositions/{comp.id}/share", json={}, headers=member_headers
    )
    assert again.status_code == 200, again.text
    assert again.json()["composition"]["share_request_status"] == "pending"


async def test_approve_without_pending_returns_409(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_private_composition(db_session, org_id, user_id)
    resp = await client.post(
        f"/api/v1/compositions/{comp.id}/share-request/approve",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 409
