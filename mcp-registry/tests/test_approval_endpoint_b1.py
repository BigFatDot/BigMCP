"""Phase B-1.4 chunk 2: REST endpoints for the approval flow.

Three endpoints:
- ``POST /executions/{id}/approve``     — cross-user resume, decision='approved'
- ``POST /executions/{id}/reject``      — cross-user resume, decision='rejected'
- ``GET  /executions/pending-approvals`` — filtered queue for the actor

All gates collapse to a uniform 403 on permission failure (no
information leak about row existence / state / which gate failed).
The audit trail keeps the precise reason for the auditor.
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.composition_execution import (
    CompositionExecution,
    ExecutionStatus,
)
from app.models.organization import OrganizationMember, UserRole
from app.models.user import User
from app.orchestration.resumable_executor import (
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)


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


async def _make_composition(
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str, step: dict,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1.4 approval endpoint",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=[step],
        data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        server_bindings={},
        allowed_roles=[],
        force_org_credentials=False,
        status=CompositionStatus.PRODUCTION.value,
        ttl=None,
        extra_metadata={},
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


async def _register_and_join_org(
    client: AsyncClient,
    db: AsyncSession,
    *,
    email: str,
    organization_id: UUID,
    role: UserRole = UserRole.ADMIN,
) -> Tuple[UUID, str]:
    """Register a fresh user and add them to ``organization_id``.

    Returns ``(user_id, bearer_token)``. Marks ``email_verified`` so
    the login succeeds regardless of edition.
    """
    from sqlalchemy import update as _update
    from uuid import uuid4 as _uuid4

    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecondaryPass123",
            "name": "Secondary User",
        },
    )
    assert register.status_code in (201, 202), register.text

    await db.execute(
        _update(User)
        .where(User.email == email.lower())
        .values(email_verified=True)
    )
    await db.commit()

    new_user = (
        await db.execute(select(User).where(User.email == email.lower()))
    ).scalar_one()

    # Drop any auto-created personal org membership(s) and attach to
    # the target org instead. (We could keep both; this just keeps
    # the test simpler.)
    await db.execute(
        OrganizationMember.__table__.delete().where(
            OrganizationMember.user_id == new_user.id
        )
    )
    db.add(
        OrganizationMember(
            id=_uuid4(),
            organization_id=organization_id,
            user_id=new_user.id,
            role=role,
        )
    )
    await db.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecondaryPass123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return new_user.id, token


@pytest.fixture(autouse=True)
def _fresh_executor():
    _reset_executor_for_tests()
    yield
    _reset_executor_for_tests()


@pytest.fixture(autouse=True)
def _patch_session_local(db_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession as _AS, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(db_engine, class_=_AS, expire_on_commit=False)
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


async def _setup_pending_approval(
    db: AsyncSession,
    *,
    launcher_id: UUID,
    org_id: UUID,
    approver_user_ids: list | None = None,
    allowed_roles: list | None = None,
    response_schema: dict | None = None,
    allow_self_approval: bool = False,
) -> UUID:
    step: dict = {
        "step_id": "ask",
        "type": "approval",
        "approval": {
            "message": "ok?",
            "approver_user_ids": approver_user_ids or [],
            "allowed_roles": allowed_roles or [],
            "allow_self_approval": allow_self_approval,
        },
    }
    if response_schema is not None:
        step["approval"]["response_schema"] = response_schema
    comp = await _make_composition(
        db, org_id, launcher_id,
        name=f"b1_approval_{uuid4().hex[:6]}",
        step=step,
    )
    eid = await create_execution(
        composition_id=comp.id,
        user_id=launcher_id,
        organization_id=org_id,
        trigger="manual",
    )
    await get_executor().run(eid)
    return eid


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_approver_in_user_id_list_can_approve(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    approver_id, approver_token = await _register_and_join_org(
        client, db_session,
        email="approver-uid@example.com",
        organization_id=org_id,
        role=UserRole.MEMBER,
    )
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id,
        org_id=org_id,
        approver_user_ids=[str(approver_id)],
    )

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {approver_token}"},
        json={"extra_fields": {}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "approved"
    assert body["status"] == ExecutionStatus.COMPLETED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    result = (row.state or {}).get("step_results", {}).get("ask")
    assert result["decision"] == "approved"
    assert result["approved_by"] == str(approver_id)


async def test_approver_matched_by_role_can_approve(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    _, approver_token = await _register_and_join_org(
        client, db_session,
        email="approver-role@example.com",
        organization_id=org_id,
        role=UserRole.ADMIN,
    )
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
    )

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp.status_code == 200


async def test_reject_carries_decision_into_step_result(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    _, approver_token = await _register_and_join_org(
        client, db_session,
        email="rejecter@example.com",
        organization_id=org_id,
        role=UserRole.ADMIN,
    )
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
    )

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/reject",
        headers={"Authorization": f"Bearer {approver_token}"},
        json={"extra_fields": {"rationale": "policy violation"}},
    )
    assert resp.status_code == 200
    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    result = (row.state or {}).get("step_results", {}).get("ask")
    assert result["decision"] == "rejected"
    assert result["rationale"] == "policy violation"


# ---------------------------------------------------------------------------
# Permission failures (uniform 403)
# ---------------------------------------------------------------------------


async def test_unrelated_user_gets_403(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """Caller is in the right org but not in the approver gate."""
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    # Approver gate references a different user_id; current user is
    # a MEMBER (not in allowed_roles below).
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        approver_user_ids=[str(uuid4())],
        allowed_roles=["admin"],  # launcher is OWNER but four-eyes blocks anyway
    )

    # Use a fresh non-launcher MEMBER
    _, member_token = await _register_and_join_org(
        client, db_session,
        email="random-member@example.com",
        organization_id=org_id,
        role=UserRole.MEMBER,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


async def test_launcher_self_approval_blocked_by_default(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """The launcher (registered as ADMIN of their own auto-created org)
    cannot satisfy an ``allowed_roles=['admin']`` gate while
    ``allow_self_approval=False`` — the four-eyes guard fires before
    the role match."""
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
        allow_self_approval=False,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_launcher_self_approval_allowed_when_opted_in(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """With ``allow_self_approval=True`` the four-eyes guard is
    disabled, and the launcher's ADMIN role satisfies the
    ``allowed_roles=['admin']`` gate."""
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
        allow_self_approval=True,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers=auth_headers,
    )
    assert resp.status_code == 200


async def test_cross_org_attempt_gets_403(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    """Approver outside the execution's org → 403 (no info leak)."""
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    # Register a user in a DIFFERENT org. We just don't add them to
    # org_id — the standard register flow gives them their own org.
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "outsider@example.com",
            "password": "OutsiderPass123",
            "name": "Outsider",
        },
    )
    assert register.status_code in (201, 202)
    from sqlalchemy import update as _update
    await db_session.execute(
        _update(User)
        .where(User.email == "outsider@example.com")
        .values(email_verified=True)
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "outsider@example.com", "password": "OutsiderPass123"},
    )
    outsider_token = login.json()["access_token"]

    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["owner", "admin", "member"],  # very permissive on role
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    # Even though role would match, the cross-org check fires first.
    assert resp.status_code == 403


async def test_unknown_execution_gets_403(
    client: AsyncClient, auth_headers: dict,
):
    resp = await client.post(
        f"/api/v1/compositions/executions/{uuid4()}/approve",
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_not_suspended_execution_gets_403(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """Execution exists but is RUNNING (not suspended) → 403, no leak."""
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, launcher_id, name="b1_running_not_approved",
        step={"step_id": "1", "type": "tool", "tool": "noop"},
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=launcher_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Schema-validated extra_fields
# ---------------------------------------------------------------------------


async def test_approve_with_extra_fields_validated_accept(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    _, token = await _register_and_join_org(
        client, db_session,
        email="schema-ok@example.com",
        organization_id=org_id,
        role=UserRole.ADMIN,
    )
    schema = {
        "type": "object",
        "properties": {"rationale": {"type": "string"}},
        "required": ["rationale"],
    }
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
        response_schema=schema,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"extra_fields": {"rationale": "OK"}},
    )
    assert resp.status_code == 200


async def test_approve_with_invalid_extra_fields_422_keeps_suspended(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    _, token = await _register_and_join_org(
        client, db_session,
        email="schema-bad@example.com",
        organization_id=org_id,
        role=UserRole.ADMIN,
    )
    schema = {
        "type": "object",
        "properties": {"rationale": {"type": "string"}},
        "required": ["rationale"],
    }
    eid = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
        response_schema=schema,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"extra_fields": {}},  # missing required
    )
    assert resp.status_code == 422

    # Row stays suspended so the approver can retry
    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.SUSPENDED.value


# ---------------------------------------------------------------------------
# Pending-approvals listing
# ---------------------------------------------------------------------------


async def test_pending_approvals_visible_only_to_authorised_approvers(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    launcher_id, org_id = await _ids(db_session, test_user["email"])
    approver_id, approver_token = await _register_and_join_org(
        client, db_session,
        email="lister@example.com",
        organization_id=org_id,
        role=UserRole.ADMIN,
    )
    # A pending approval the approver CAN act on (role match)
    eid_for_me = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        allowed_roles=["admin"],
    )
    # A pending approval the approver CANNOT act on (specific other user_id)
    eid_not_for_me = await _setup_pending_approval(
        db_session,
        launcher_id=launcher_id, org_id=org_id,
        approver_user_ids=[str(uuid4())],
    )

    resp = await client.get(
        "/api/v1/compositions/executions/pending-approvals",
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert str(eid_for_me) in ids
    assert str(eid_not_for_me) not in ids
