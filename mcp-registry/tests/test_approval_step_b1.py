"""Phase B-1.4 chunk 1: ``approval`` step type — config + dispatch + permission.

REST endpoint tests live in test_approval_endpoint_b1.py to keep the
unit-level surface isolated from the JWT/org-membership plumbing.
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
from app.orchestration.approval_step import (
    ApprovalConfigError,
    build_response_envelope,
    build_suspend,
    can_approve,
    validate_config,
    validate_response_schema,
)
from app.orchestration.composition_routing import SUSPENDING_STEP_TYPES
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    INPUTS_KEY,
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
    db: AsyncSession, org_id: UUID, owner_id: UUID, *, name: str, steps: list,
) -> Composition:
    comp = Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1.4 approval",
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
# Sanity
# ---------------------------------------------------------------------------


def test_approval_in_suspending_step_types():
    assert "approval" in SUSPENDING_STEP_TYPES


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_requires_object():
    with pytest.raises(ApprovalConfigError):
        validate_config(None)


def test_validate_requires_message():
    with pytest.raises(ApprovalConfigError):
        validate_config({"approver_user_ids": [str(uuid4())]})


def test_validate_requires_at_least_one_approver_arm():
    with pytest.raises(ApprovalConfigError):
        validate_config({"message": "ok?"})


def test_validate_accepts_user_ids_only():
    validate_config({
        "message": "ok?",
        "approver_user_ids": [str(uuid4())],
    })


def test_validate_accepts_roles_only():
    validate_config({
        "message": "ok?",
        "allowed_roles": ["admin"],
    })


def test_validate_accepts_both_arms():
    validate_config({
        "message": "ok?",
        "approver_user_ids": [str(uuid4())],
        "allowed_roles": ["owner"],
    })


def test_validate_rejects_unknown_role():
    with pytest.raises(ApprovalConfigError):
        validate_config({
            "message": "ok?",
            "allowed_roles": ["chairman"],
        })


def test_validate_rejects_invalid_uuid():
    with pytest.raises(ApprovalConfigError):
        validate_config({
            "message": "ok?",
            "approver_user_ids": ["not-a-uuid"],
        })


def test_validate_rejects_non_dict_response_schema():
    with pytest.raises(ApprovalConfigError):
        validate_config({
            "message": "ok?",
            "allowed_roles": ["admin"],
            "response_schema": "bogus",
        })


def test_validate_rejects_response_schema_without_type():
    with pytest.raises(ApprovalConfigError):
        validate_config({
            "message": "ok?",
            "allowed_roles": ["admin"],
            "response_schema": {"properties": {"r": {"type": "string"}}},
        })


def test_validate_rejects_non_bool_self_approval():
    with pytest.raises(ApprovalConfigError):
        validate_config({
            "message": "ok?",
            "allowed_roles": ["admin"],
            "allow_self_approval": "yes",
        })


def test_validate_normalises_case_and_dedup():
    """Author can pass 'Admin' / 'ADMIN' / duplicates — we normalise."""
    validate_config({
        "message": "ok?",
        "allowed_roles": ["Admin", "ADMIN", "admin"],
    })


# ---------------------------------------------------------------------------
# Permission checks (can_approve)
# ---------------------------------------------------------------------------


def test_can_approve_matches_user_id():
    approver = uuid4()
    payload = {
        "approver_user_ids": [str(approver)],
        "allowed_roles": [],
        "launcher_user_id": str(uuid4()),
        "allow_self_approval": False,
    }
    ok, _ = can_approve(payload, actor_user_id=approver, actor_role="member")
    assert ok is True


def test_can_approve_matches_role():
    payload = {
        "approver_user_ids": [],
        "allowed_roles": ["admin"],
        "launcher_user_id": str(uuid4()),
        "allow_self_approval": False,
    }
    ok, _ = can_approve(payload, actor_user_id=uuid4(), actor_role="ADMIN")
    assert ok is True


def test_can_approve_rejects_unrelated_user():
    payload = {
        "approver_user_ids": [str(uuid4())],
        "allowed_roles": ["admin"],
        "launcher_user_id": str(uuid4()),
        "allow_self_approval": False,
    }
    ok, reason = can_approve(payload, actor_user_id=uuid4(), actor_role="member")
    assert ok is False
    assert reason == "not_in_approver_set"


def test_can_approve_four_eyes_default_denies_launcher():
    launcher = uuid4()
    payload = {
        "approver_user_ids": [str(launcher)],
        "allowed_roles": [],
        "launcher_user_id": str(launcher),
        "allow_self_approval": False,
    }
    ok, reason = can_approve(payload, actor_user_id=launcher, actor_role="owner")
    assert ok is False
    assert reason == "self_approval_disallowed"


def test_can_approve_opt_in_self_approval_allows_launcher():
    launcher = uuid4()
    payload = {
        "approver_user_ids": [str(launcher)],
        "allowed_roles": [],
        "launcher_user_id": str(launcher),
        "allow_self_approval": True,
    }
    ok, _ = can_approve(payload, actor_user_id=launcher, actor_role="member")
    assert ok is True


def test_can_approve_self_approval_blocks_role_match_too():
    """Four-eyes also blocks the launcher matching via the role arm."""
    launcher = uuid4()
    payload = {
        "approver_user_ids": [],
        "allowed_roles": ["admin"],
        "launcher_user_id": str(launcher),
        "allow_self_approval": False,
    }
    ok, reason = can_approve(payload, actor_user_id=launcher, actor_role="admin")
    assert ok is False
    assert reason == "self_approval_disallowed"


# ---------------------------------------------------------------------------
# Response envelope assembly
# ---------------------------------------------------------------------------


def test_response_envelope_always_carries_server_fields():
    actor = uuid4()
    out = build_response_envelope(
        decision="approved",
        actor_user_id=actor,
        suspension_payload={},
        extra_fields={"rationale": "looks good"},
    )
    assert out["decision"] == "approved"
    assert out["approved_by"] == str(actor)
    assert out["rationale"] == "looks good"
    assert out["approved_at"].endswith("Z")


def test_response_envelope_strips_attempted_field_spoofing():
    """Author/approver CANNOT shadow decision/approved_by/approved_at."""
    out = build_response_envelope(
        decision="approved",
        actor_user_id=uuid4(),
        suspension_payload={},
        extra_fields={
            "decision": "rejected",  # spoofing attempt
            "approved_by": str(uuid4()),
            "approved_at": "1970-01-01T00:00:00Z",
            "rationale": "kept",
        },
    )
    assert out["decision"] == "approved"
    assert out["rationale"] == "kept"
    # approved_by + approved_at are server-set, not the spoofed values
    assert out["approved_at"] != "1970-01-01T00:00:00Z"


def test_validate_response_schema_passthrough_when_no_schema():
    ok, err = validate_response_schema({}, {"any": "thing"})
    assert ok is True
    assert err is None


def test_validate_response_schema_enforces_required():
    payload = {
        "response_schema": {
            "type": "object",
            "properties": {"rationale": {"type": "string"}},
            "required": ["rationale"],
        }
    }
    ok, err = validate_response_schema(payload, {})
    assert ok is False
    assert "rationale" in (err or "")


# ---------------------------------------------------------------------------
# build_suspend — prompt resolution + payload shape
# ---------------------------------------------------------------------------


def test_build_suspend_resolves_prompt():
    launcher = uuid4()
    approver = uuid4()
    step = {
        "step_id": "ask_mgr",
        "type": "approval",
        "approval": {
            "message": "Approve deletion of ${input.target}?",
            "approver_user_ids": [str(approver)],
        },
    }
    state = ExecutionState(step_results={INPUTS_KEY: {"target": "record_42"}})
    out = build_suspend(step, state, launcher_user_id=launcher)
    assert out.reason == "approval"
    assert out.payload["step_id"] == "ask_mgr"
    assert out.payload["message"] == "Approve deletion of record_42?"
    assert out.payload["launcher_user_id"] == str(launcher)
    assert out.payload["approver_user_ids"] == [str(approver)]
    assert out.payload["allowed_roles"] == []
    assert out.payload["allow_self_approval"] is False


def test_build_suspend_carries_response_schema():
    schema = {
        "type": "object",
        "properties": {"rationale": {"type": "string"}},
    }
    step = {
        "step_id": "ask",
        "type": "approval",
        "approval": {
            "message": "ok?",
            "allowed_roles": ["admin"],
            "response_schema": schema,
        },
    }
    out = build_suspend(step, ExecutionState(), launcher_user_id=uuid4())
    assert out.payload["response_schema"] == schema


# ---------------------------------------------------------------------------
# End-to-end via the executor
# ---------------------------------------------------------------------------


async def test_executor_yields_with_approval_suspension(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_approval_yield",
        steps=[{
            "step_id": "ask",
            "type": "approval",
            "approval": {
                "message": "Approve?",
                "allowed_roles": ["admin", "owner"],
                "ttl_seconds": 1800,
            },
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.SUSPENDED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    susp = (row.state or {}).get("suspension") or {}
    assert susp.get("reason") == "approval"
    payload = susp.get("payload") or {}
    assert payload.get("allowed_roles") == ["admin", "owner"]
    assert payload.get("launcher_user_id") == str(user_id)
    # TTL applied
    assert row.expires_at is not None


async def test_executor_resume_completes_with_envelope_in_step_result(
    db_session: AsyncSession, test_user: dict
):
    """Manual executor.resume — same effect the REST endpoint will produce."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_approval_resume",
        steps=[{
            "step_id": "ask",
            "type": "approval",
            "approval": {
                "message": "ok?",
                "approver_user_ids": [str(uuid4())],
            },
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    await executor.run(eid)

    # Simulate the endpoint having validated + built the envelope
    actor = uuid4()
    envelope = build_response_envelope(
        decision="approved",
        actor_user_id=actor,
        suspension_payload={},
        extra_fields={},
    )
    final = await executor.resume(eid, envelope)
    assert final == ExecutionStatus.COMPLETED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    result = row.state["step_results"]["ask"]
    assert result["decision"] == "approved"
    assert result["approved_by"] == str(actor)
    assert result["approved_at"].endswith("Z")


async def test_executor_malformed_config_fails_step(
    db_session: AsyncSession, test_user: dict
):
    """No approver arms → dispatch raises → step fails."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_approval_bad",
        steps=[{
            "step_id": "ask",
            "type": "approval",
            "approval": {"message": "ok?"},  # missing approver arm
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    status_str = await get_executor().run(eid)
    assert status_str == ExecutionStatus.FAILED.value
