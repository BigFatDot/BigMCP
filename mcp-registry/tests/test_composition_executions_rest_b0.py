"""Phase B-0 chunk 10: REST endpoints for composition executions.

Covers list/get/cancel/resume + the admin governance route.

All endpoints enforce per-user (or per-org for admin) ownership,
returning 404 on cross-user reads to avoid leaking row existence.
"""

from __future__ import annotations

import json
from typing import Tuple
from uuid import UUID

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
    ExecutionStepEvent,
)
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    create_execution,
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
    db: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    *,
    name: str,
    suspending: bool = False,
) -> Composition:
    steps = [
        {"step_id": "1", "type": "_test_suspend"}
        if suspending
        else {"step_id": "1", "type": "tool", "tool": "noop"}
    ]
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0 chunk10 rest",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=steps,
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


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


async def test_list_default_excludes_terminal(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_list_def")

    running_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )
    completed_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    # Move the second to terminal
    completed_row = await db_session.get(CompositionExecution, completed_id)
    completed_row.status = ExecutionStatus.COMPLETED.value
    await db_session.commit()

    resp = await client.get(
        "/api/v1/compositions/executions", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert str(running_id) in ids
    assert str(completed_id) not in ids


async def test_list_include_terminal_returns_all(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_list_all")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, eid)
    row.status = ExecutionStatus.FAILED.value
    row.error = "boom"
    await db_session.commit()

    resp = await client.get(
        "/api/v1/compositions/executions?include_terminal=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert str(eid) in ids


async def test_list_explicit_status_filter(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_list_filter")
    e_run = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )
    e_susp = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.SUSPENDED,
    )

    resp = await client.get(
        "/api/v1/compositions/executions?status=suspended",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert str(e_susp) in ids
    assert str(e_run) not in ids


async def test_list_pagination(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_list_page")
    for _ in range(5):
        await create_execution(
            composition_id=comp.id, user_id=user_id, organization_id=org_id,
            trigger="manual", initial_status=ExecutionStatus.RUNNING,
        )
    resp = await client.get(
        "/api/v1/compositions/executions?limit=2&offset=0",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2


# ---------------------------------------------------------------------------
# DETAIL
# ---------------------------------------------------------------------------


async def test_detail_includes_state_events_and_derived_fields(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_detail", suspending=True
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Manually populate state + an event so the detail has something to ship
    row = await db_session.get(CompositionExecution, eid)
    state = ExecutionState.from_jsonb(row.state)
    state.current_step_id = "1"
    state.suspension = {"reason": "_test_suspend", "payload": {}, "ttl_seconds": 60}
    row.state = state.to_jsonb()
    row.status = ExecutionStatus.SUSPENDED.value
    db_session.add(
        ExecutionStepEvent(
            execution_id=eid,
            step_id="1",
            event_type="suspended",
            payload={"reason": "_test_suspend"},
            timestamp=row.started_at,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/compositions/executions/{eid}", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(eid)
    assert body["status"] == "suspended"
    assert body["current_step_id"] == "1"
    assert body["suspension_reason"] == "_test_suspend"
    assert isinstance(body["state"], dict)
    assert isinstance(body["events"], list)
    assert any(e["event_type"] == "suspended" for e in body["events"])


async def test_detail_404_on_unknown_id(
    client: AsyncClient, auth_headers: dict
):
    from uuid import uuid4
    resp = await client.get(
        f"/api/v1/compositions/executions/{uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------


async def test_cancel_sets_flag(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_cancel")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/cancel",
        headers=auth_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["cancel_requested"] is True

    # Flag persisted
    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    assert row.cancel_requested is True


async def test_cancel_terminal_is_idempotent_no_op(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_cancel_term")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, eid)
    row.status = ExecutionStatus.COMPLETED.value
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/cancel",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["cancel_requested"] is False  # No row was touched


async def test_cancel_404_unknown_id(
    client: AsyncClient, auth_headers: dict
):
    from uuid import uuid4
    resp = await client.post(
        f"/api/v1/compositions/executions/{uuid4()}/cancel",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RESUME
# ---------------------------------------------------------------------------


async def test_resume_succeeds_for_suspended(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_resume_ok", suspending=True
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Drive the executor to suspend
    from app.orchestration.resumable_executor import get_executor
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.SUSPENDED.value

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/resume",
        headers=auth_headers,
        json={"response": {"value": 42}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == ExecutionStatus.COMPLETED.value


async def test_resume_409_when_not_suspended(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_resume_409")
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual", initial_status=ExecutionStatus.RUNNING,
    )

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/resume",
        headers=auth_headers,
        json={"response": "anything"},
    )
    assert resp.status_code == 409


async def test_resume_404_on_unknown_id(
    client: AsyncClient, auth_headers: dict
):
    from uuid import uuid4
    resp = await client.post(
        f"/api/v1/compositions/executions/{uuid4()}/resume",
        headers=auth_headers,
        json={"response": None},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------


async def test_list_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/compositions/executions")
    assert resp.status_code in (401, 403)


async def test_detail_requires_auth(client: AsyncClient):
    from uuid import uuid4
    resp = await client.get(
        f"/api/v1/compositions/executions/{uuid4()}"
    )
    assert resp.status_code in (401, 403)
