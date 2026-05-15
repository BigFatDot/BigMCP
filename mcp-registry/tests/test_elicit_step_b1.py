"""Phase B-1 chunk 1: ``elicit`` step type — executor dispatch + validation.

Covers the suspension shape, prompt resolution, TTL clamping, and
schema-validated resume path documented in
``docs/composition_executions_b1.md``.
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID

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
from app.orchestration.composition_routing import SUSPENDING_STEP_TYPES
from app.orchestration.elicit_step import (
    DEFAULT_TTL_SECONDS,
    ElicitConfigError,
    MAX_TTL_SECONDS,
    coerce_ttl,
    resolve_message,
    validate_config,
    validate_response,
)
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    INPUTS_KEY,
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures + helpers
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
    steps: list,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1 elicit test",
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
# Pure helpers (sync, no DB)
# ---------------------------------------------------------------------------


def test_elicit_added_to_suspending_step_types():
    """The routing static analysis must recognise elicit as suspending."""
    assert "elicit" in SUSPENDING_STEP_TYPES


def test_coerce_ttl_defaults_when_missing():
    assert coerce_ttl(None) == DEFAULT_TTL_SECONDS


def test_coerce_ttl_rejects_below_min():
    with pytest.raises(ElicitConfigError):
        coerce_ttl(0)


def test_coerce_ttl_rejects_above_max():
    with pytest.raises(ElicitConfigError):
        coerce_ttl(MAX_TTL_SECONDS + 1)


def test_coerce_ttl_rejects_non_int():
    with pytest.raises(ElicitConfigError):
        coerce_ttl("300")
    with pytest.raises(ElicitConfigError):
        coerce_ttl(300.0)


def test_validate_config_rejects_missing_message():
    with pytest.raises(ElicitConfigError):
        validate_config({"schema": {"type": "object"}})


def test_validate_config_rejects_missing_schema():
    with pytest.raises(ElicitConfigError):
        validate_config({"message": "ok"})


def test_validate_config_rejects_schema_without_type():
    with pytest.raises(ElicitConfigError):
        validate_config({
            "message": "ok",
            "schema": {"properties": {"x": {"type": "string"}}},
        })


def test_validate_config_accepts_minimal():
    # No exception
    validate_config({
        "message": "Confirm?",
        "schema": {"type": "object"},
    })


# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------


def test_resolve_message_substitutes_input():
    state = ExecutionState(step_results={INPUTS_KEY: {"name": "Alice"}})
    assert resolve_message("Hello ${input.name}", state) == "Hello Alice"


def test_resolve_message_substitutes_step_path():
    state = ExecutionState(
        step_results={
            INPUTS_KEY: {},
            "load_record": {"title": "Project Foo", "id": 42},
        },
    )
    out = resolve_message(
        "Delete '${load_record.title}' (id ${load_record.id})?", state
    )
    assert out == "Delete 'Project Foo' (id 42)?"


def test_resolve_message_leaves_unresolved_placeholder():
    state = ExecutionState(step_results={INPUTS_KEY: {}})
    out = resolve_message("Hello ${input.missing}", state)
    assert "${input.missing}" in out


def test_resolve_message_jsonifies_complex_values():
    state = ExecutionState(
        step_results={
            INPUTS_KEY: {"items": [1, 2, 3]},
        },
    )
    out = resolve_message("Items: ${input.items}", state)
    assert out == "Items: [1, 2, 3]"


# ---------------------------------------------------------------------------
# Resume validation
# ---------------------------------------------------------------------------


def test_validate_response_accepts_matching_payload():
    payload = {"schema": {
        "type": "object",
        "properties": {"confirmed": {"type": "boolean"}},
        "required": ["confirmed"],
    }}
    ok, err = validate_response(payload, {"confirmed": True})
    assert ok is True
    assert err is None


def test_validate_response_rejects_missing_required():
    payload = {"schema": {
        "type": "object",
        "properties": {"confirmed": {"type": "boolean"}},
        "required": ["confirmed"],
    }}
    ok, err = validate_response(payload, {})
    assert ok is False
    assert "confirmed" in (err or "")


def test_validate_response_rejects_wrong_type():
    payload = {"schema": {
        "type": "object",
        "properties": {"confirmed": {"type": "boolean"}},
    }}
    ok, err = validate_response(payload, {"confirmed": "yes"})
    assert ok is False


def test_validate_response_rejects_when_schema_missing():
    ok, err = validate_response({}, {"any": "value"})
    assert ok is False


# ---------------------------------------------------------------------------
# End-to-end: executor yields + resume completes
# ---------------------------------------------------------------------------


async def test_elicit_executor_yields_with_resolved_prompt(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_elicit_yield",
        steps=[{
            "step_id": "ask",
            "type": "elicit",
            "elicit": {
                "message": "Confirm deleting ${input.target}?",
                "schema": {
                    "type": "object",
                    "properties": {"confirmed": {"type": "boolean"}},
                    "required": ["confirmed"],
                },
                "ttl_seconds": 60,
            },
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
        inputs={"target": "record_42"},
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.SUSPENDED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    susp = row.state.get("suspension") or {}
    assert susp.get("reason") == "elicit"
    payload = susp.get("payload") or {}
    assert payload.get("step_id") == "ask"
    assert payload.get("message") == "Confirm deleting record_42?"
    assert payload.get("schema", {}).get("type") == "object"
    # TTL applied to expires_at
    assert row.expires_at is not None


async def test_elicit_resume_completes_composition(
    db_session: AsyncSession, test_user: dict
):
    """Full round-trip: yield → REST-equivalent resume → completed."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_elicit_round_trip",
        steps=[{
            "step_id": "ask",
            "type": "elicit",
            "elicit": {
                "message": "Confirm?",
                "schema": {
                    "type": "object",
                    "properties": {"confirmed": {"type": "boolean"}},
                    "required": ["confirmed"],
                },
            },
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    await executor.run(eid)

    final = await executor.resume(eid, {"confirmed": True})
    assert final == ExecutionStatus.COMPLETED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    assert row.state["step_results"]["ask"] == {"confirmed": True}
    assert row.state["suspension"] is None


async def test_elicit_malformed_config_fails_step(
    db_session: AsyncSession, test_user: dict
):
    """An elicit step with a missing schema is caught at dispatch
    time and surfaces as a step failure (composition fails)."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_elicit_bad_config",
        steps=[{
            "step_id": "ask",
            "type": "elicit",
            "elicit": {"message": "Confirm?"},  # schema missing
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.FAILED.value
