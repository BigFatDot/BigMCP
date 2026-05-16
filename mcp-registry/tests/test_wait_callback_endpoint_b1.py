"""Phase B-1.5 chunk 2: REST callback endpoint — HMAC validation + resume.

Covers ``POST /api/v1/compositions/executions/{id}/callback/{token}``,
which has NO JWT (the token IS the credential). The endpoint must:

- 200 + resume on a valid token
- 401 (uniform) on bad token / wrong state / unknown execution
- 409 on a token replayed after a successful resume
- 422 on body that fails the author-declared expected_schema
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
from app.models.organization import OrganizationMember
from app.models.user import User
from app.orchestration.resumable_executor import (
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
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
        description="b1.5 callback endpoint",
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


async def _setup_suspended_wait_callback(
    db: AsyncSession, client: AsyncClient, test_user: dict,
    *, expected_schema: dict | None = None,
) -> Tuple[UUID, str]:
    """Drive an execution into wait_callback suspension. Returns
    ``(execution_id, plaintext_token_from_url)``."""
    user_id, org_id = await _ids(db, test_user["email"])
    step: dict = {"step_id": "wh", "type": "wait_callback"}
    if expected_schema is not None:
        step["wait_callback"] = {"expected_schema": expected_schema}
    comp = await _make_composition(
        db, org_id, user_id, name=f"b1_endpoint_{uuid4().hex[:6]}", step=step,
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    await get_executor().run(eid)

    row = await db.get(CompositionExecution, eid)
    await db.refresh(row)
    payload = ((row.state or {}).get("suspension") or {}).get("payload") or {}
    url = payload["callback_url"]
    token = url.rsplit("/", 1)[-1]
    return eid, token


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_callback_with_valid_token_resumes_execution(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    eid, token = await _setup_suspended_wait_callback(db_session, client, test_user)

    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={"hello": "world"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["execution_id"] == str(eid)
    assert body["status"] == ExecutionStatus.COMPLETED.value


async def test_callback_with_empty_body_resumes(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    """No body → executor treats it as `{}`. Resume still works."""
    eid, token = await _setup_suspended_wait_callback(db_session, client, test_user)
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}"
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Auth failures (all return uniform 401)
# ---------------------------------------------------------------------------


async def test_callback_with_bad_token_returns_401(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    eid, _ = await _setup_suspended_wait_callback(db_session, client, test_user)
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/wrong-token",
        json={},
    )
    assert resp.status_code == 401


async def test_callback_with_unknown_execution_returns_401(
    client: AsyncClient,
):
    resp = await client.post(
        f"/api/v1/compositions/executions/{uuid4()}/callback/any-token",
        json={},
    )
    assert resp.status_code == 401


async def test_callback_on_non_wait_callback_suspension_returns_401(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    """Execution suspended on a different reason → 401 (no info leak)."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_elicit_for_cb_neg",
        step={
            "step_id": "ask",
            "type": "elicit",
            "elicit": {"message": "ok?", "schema": {"type": "object"}},
        },
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    await get_executor().run(eid)
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/whatever",
        json={},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Replay + state conflicts
# ---------------------------------------------------------------------------


async def test_callback_replayed_after_success_returns_409(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    eid, token = await _setup_suspended_wait_callback(db_session, client, test_user)
    # First fire — succeeds, execution completes
    first = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={},
    )
    assert first.status_code == 200
    # Replay
    second = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={},
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Body schema validation
# ---------------------------------------------------------------------------


async def test_callback_body_validated_against_expected_schema_reject(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    eid, token = await _setup_suspended_wait_callback(
        db_session, client, test_user, expected_schema=schema,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={},  # missing required
    )
    assert resp.status_code == 422
    # Execution stays suspended so the caller can retry
    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    assert row.status == ExecutionStatus.SUSPENDED.value


async def test_callback_body_validated_against_expected_schema_accept(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    eid, token = await _setup_suspended_wait_callback(
        db_session, client, test_user, expected_schema=schema,
    )
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={"status": "done"},
    )
    assert resp.status_code == 200


async def test_callback_endpoint_does_not_require_jwt(
    client: AsyncClient, db_session: AsyncSession, test_user: dict,
):
    """Sanity: no Authorization header is needed (the token IS the
    credential). Failing this test means we accidentally gated the
    webhook behind JWT — external systems would never reach it."""
    eid, token = await _setup_suspended_wait_callback(db_session, client, test_user)
    resp = await client.post(
        f"/api/v1/compositions/executions/{eid}/callback/{token}",
        json={},
        # no Authorization header
    )
    assert resp.status_code == 200
