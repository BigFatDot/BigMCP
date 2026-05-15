"""Phase B-0 chunk 8: composition_status meta-tool tests.

Validates the per-user scoping rule (cross-user → not_found, no leak)
and the summary shape across all execution states.
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID, uuid4

import pytest
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
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    create_execution,
    _reset_executor_for_tests,
)
from app.routers.mcp_gateway.pool import (
    POOL_TOOL_NAMES,
    get_pool_tools,
    handle_composition_status,
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
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b0 status test",
        visibility=CompositionVisibility.PRIVATE.value,
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
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
    """Make ``create_execution`` see the test SQLite engine.

    Same pattern as test_resumable_executor.py: the helpers in
    resumable_executor open their own session via the module-level
    ``AsyncSessionLocal``. We swap that for a sessionmaker bound to
    the in-memory SQLite engine so the data the helper writes is
    visible to the assertions in this test session.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.db import session as session_module

    test_factory = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(session_module, "AsyncSessionLocal", test_factory)
    yield test_factory


# ---------------------------------------------------------------------------
# Definitions tests (sync — pytestmark covers both)
# ---------------------------------------------------------------------------


def test_composition_status_in_pool_tool_names():
    assert "composition_status" in POOL_TOOL_NAMES


def test_composition_status_definition_shape():
    tools = get_pool_tools()
    by_name = {t["name"]: t for t in tools}
    assert "composition_status" in by_name
    spec = by_name["composition_status"]
    # Required input
    assert spec["inputSchema"]["required"] == ["execution_id"]
    # Output enum includes the not_found sentinel
    enum = spec["outputSchema"]["properties"]["status"]["enum"]
    assert "not_found" in enum
    for value in (
        "queued", "running", "suspended", "completed",
        "failed", "expired", "cancelled",
    ):
        assert value in enum
    # Read-only / idempotent annotation contract
    assert spec["annotations"]["readOnlyHint"] is True
    assert spec["annotations"]["idempotentHint"] is True
    assert spec["annotations"]["destructiveHint"] is False


# ---------------------------------------------------------------------------
# Handler tests
# ---------------------------------------------------------------------------


async def test_status_returns_summary_for_owner(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_status_owner")
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Default state at creation is RUNNING
    response = await handle_composition_status(
        {"execution_id": str(execution_id)},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = response["structuredContent"]
    assert body["execution_id"] == str(execution_id)
    assert body["status"] == ExecutionStatus.RUNNING.value
    assert body["error"] is None
    assert body["result_uri"] is None
    assert body["started_at"] is not None
    assert body["updated_at"] is not None


async def test_status_completed_includes_result_uri(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_status_done")
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )

    # Manually move to completed
    row = await db_session.get(CompositionExecution, execution_id)
    row.status = ExecutionStatus.COMPLETED.value
    await db_session.commit()

    response = await handle_composition_status(
        {"execution_id": str(execution_id)},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = response["structuredContent"]
    assert body["status"] == ExecutionStatus.COMPLETED.value
    assert body["result_uri"] == f"composition://executions/{execution_id}"


async def test_status_suspended_surfaces_reason(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b0_status_suspend"
    )
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, execution_id)
    state = ExecutionState.from_jsonb(row.state)
    state.current_step_id = "1"
    state.suspension = {
        "reason": "elicit",
        "payload": {"prompt": "Confirm please"},
        "ttl_seconds": 60,
    }
    row.state = state.to_jsonb()
    row.status = ExecutionStatus.SUSPENDED.value
    await db_session.commit()

    response = await handle_composition_status(
        {"execution_id": str(execution_id)},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = response["structuredContent"]
    assert body["status"] == ExecutionStatus.SUSPENDED.value
    assert body["current_step_id"] == "1"
    assert body["suspension_reason"] == "elicit"
    assert body["result_uri"] is None


async def test_status_failed_surfaces_error(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(db_session, org_id, user_id, name="b0_status_fail")
    execution_id = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    row = await db_session.get(CompositionExecution, execution_id)
    row.status = ExecutionStatus.FAILED.value
    row.error = "upstream timed out"
    await db_session.commit()

    response = await handle_composition_status(
        {"execution_id": str(execution_id)},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = response["structuredContent"]
    assert body["status"] == ExecutionStatus.FAILED.value
    assert body["error"] == "upstream timed out"
    assert body["result_uri"] is None


async def test_status_cross_user_returns_not_found(
    db_session: AsyncSession, test_user: dict
):
    """A user cannot probe the existence of someone else's execution.

    Creates a second user inline (the conftest only ships one).
    """
    owner_id, owner_org = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, owner_org, owner_id, name="b0_status_cross_user"
    )
    execution_id = await create_execution(
        composition_id=comp.id,
        user_id=owner_id,
        organization_id=owner_org,
        trigger="manual",
    )

    # Forge an "other" user_id — any valid UUID that doesn't match the
    # owner is enough to exercise the per-user filter; the handler
    # never validates that the user_id exists in the users table
    # (that's enforced upstream by JWT/API-key auth).
    intruder_id = uuid4()
    response = await handle_composition_status(
        {"execution_id": str(execution_id)},
        user_id=str(intruder_id),
        organization_id=str(owner_org),  # even with the right org
        db=db_session,
    )
    body = response["structuredContent"]
    assert body["status"] == "not_found"
    assert body["execution_id"] == str(execution_id)
    assert body["error"] is None
    assert body["result_uri"] is None


async def test_status_unknown_uuid_returns_not_found(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    bogus = uuid4()
    response = await handle_composition_status(
        {"execution_id": str(bogus)},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    assert response["structuredContent"]["status"] == "not_found"


async def test_status_invalid_uuid_returns_not_found(
    db_session: AsyncSession, test_user: dict
):
    """Non-UUID inputs are surfaced as not_found, not as crashes."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    response = await handle_composition_status(
        {"execution_id": "not-a-uuid"},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    assert response["structuredContent"]["status"] == "not_found"
    # Echo the input verbatim so the LLM can debug
    assert response["structuredContent"]["execution_id"] == "not-a-uuid"


async def test_status_missing_argument_is_error(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    response = await handle_composition_status(
        {},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    assert response.get("isError") is True
    assert response["structuredContent"]["status"] == "not_found"
