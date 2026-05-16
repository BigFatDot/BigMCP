"""Unit tests for the input_schema validation guarding promotion to production."""

from app.services.composition_service import _validate_input_schema_for_production


class _Comp:
    def __init__(self, input_schema, steps):
        self.input_schema = input_schema
        self.steps = steps


def test_valid_when_no_params_referenced_and_empty_schema():
    err = _validate_input_schema_for_production(
        _Comp(input_schema={}, steps=[{"tool": "noop", "params": {}}])
    )
    assert err is None


def test_valid_when_all_params_declared():
    schema = {
        "type": "object",
        "properties": {"foo": {"type": "string"}, "bar": {"type": "integer"}},
        "required": ["foo"],
    }
    steps = [{"tool": "x", "params": {"a": "${input.foo}", "b": "${input.bar}"}}]
    assert _validate_input_schema_for_production(_Comp(schema, steps)) is None


def test_rejects_missing_property():
    schema = {"type": "object", "properties": {"foo": {"type": "string"}}}
    steps = [{"tool": "x", "params": {"a": "${input.foo}", "b": "${input.missing}"}}]
    err = _validate_input_schema_for_production(_Comp(schema, steps))
    assert err is not None
    assert "missing" in err


def test_rejects_non_object_type():
    schema = {"type": "array", "properties": {}}
    err = _validate_input_schema_for_production(_Comp(schema, []))
    assert err is not None
    assert "object" in err


def test_rejects_null_schema():
    err = _validate_input_schema_for_production(_Comp(None, []))
    assert err is not None


def test_rejects_non_dict_schema():
    err = _validate_input_schema_for_production(_Comp("not a dict", []))
    assert err is not None


def test_rejects_non_dict_properties():
    err = _validate_input_schema_for_production(_Comp({"properties": "oops"}, []))
    assert err is not None


def test_ignores_legacy_parameters_prefix():
    """Regression: the validator used to LOOK for ``${parameters.X}`` instead
    of ``${input.X}`` (the actual runtime convention). Refs using the legacy
    prefix should NOT be treated as referenced parameters — they would never
    be substituted at exec time anyway, and a wrapper using only ``${input.X}``
    references should still pass when its declarations match."""
    schema = {"type": "object", "properties": {"date": {"type": "string"}}}
    steps = [
        {
            "step_id": "1",
            "tool": "Calendar__add_event",
            "parameters": {
                "when": "${input.date}",
                # Legacy / wrong prefix — must be ignored, not flagged as
                # missing.
                "_legacy": "${parameters.unused}",
            },
        }
    ]
    assert _validate_input_schema_for_production(_Comp(schema, steps)) is None


# ---------------------------------------------------------------------------
# B-1 chunk 4: elicit step validation at promote time
# ---------------------------------------------------------------------------


from app.services.composition_service import _validate_elicit_steps_for_production


def test_elicit_valid_passes():
    steps = [{
        "step_id": "ask",
        "type": "elicit",
        "elicit": {
            "message": "Confirm?",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
        },
    }]
    assert _validate_elicit_steps_for_production(_Comp({}, steps)) is None


def test_elicit_missing_message_rejected():
    steps = [{
        "step_id": "ask",
        "type": "elicit",
        "elicit": {"schema": {"type": "object"}},
    }]
    err = _validate_elicit_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "ask" in err and "message" in err


def test_elicit_missing_schema_rejected():
    steps = [{
        "step_id": "ask",
        "type": "elicit",
        "elicit": {"message": "Confirm?"},
    }]
    err = _validate_elicit_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "schema" in err


def test_elicit_schema_without_type_rejected():
    steps = [{
        "step_id": "ask",
        "type": "elicit",
        "elicit": {
            "message": "Pick one",
            "schema": {"properties": {"x": {"type": "string"}}},
        },
    }]
    err = _validate_elicit_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "type" in err


def test_elicit_ttl_out_of_range_rejected():
    steps = [{
        "step_id": "ask",
        "type": "elicit",
        "elicit": {
            "message": "Confirm?",
            "schema": {"type": "object"},
            "ttl_seconds": 10**6,  # > 24h cap
        },
    }]
    err = _validate_elicit_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "ttl_seconds" in err


def test_elicit_validator_ignores_non_elicit_steps():
    steps = [
        {"step_id": "1", "type": "tool", "tool": "noop"},
        {"step_id": "2", "type": "_test_suspend"},
    ]
    assert _validate_elicit_steps_for_production(_Comp({}, steps)) is None


def test_elicit_validator_handles_step_without_step_id():
    """Falls back to ``step #N`` in the error label."""
    steps = [{"type": "elicit", "elicit": {"message": "x"}}]
    err = _validate_elicit_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "#0" in err


# ---------------------------------------------------------------------------
# B-1.2 chunk 3: wait_until step validation at promote time
# ---------------------------------------------------------------------------


from datetime import datetime, timedelta

from app.services.composition_service import _validate_wait_until_steps_for_production


def test_wait_until_valid_relative_passes():
    steps = [{
        "step_id": "wait",
        "type": "wait_until",
        "wait_until": {"wait_seconds": 60},
    }]
    assert _validate_wait_until_steps_for_production(_Comp({}, steps)) is None


def test_wait_until_valid_absolute_passes():
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    steps = [{
        "step_id": "wait",
        "type": "wait_until",
        "wait_until": {"resume_at": future},
    }]
    assert _validate_wait_until_steps_for_production(_Comp({}, steps)) is None


def test_wait_until_missing_both_rejected():
    steps = [{
        "step_id": "wait",
        "type": "wait_until",
        "wait_until": {},
    }]
    err = _validate_wait_until_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "wait" in err


def test_wait_until_both_forms_rejected():
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    steps = [{
        "step_id": "wait",
        "type": "wait_until",
        "wait_until": {"wait_seconds": 60, "resume_at": future},
    }]
    err = _validate_wait_until_steps_for_production(_Comp({}, steps))
    assert err is not None
    assert "mutually exclusive" in err


def test_wait_until_absolute_in_past_rejected():
    past = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"
    steps = [{
        "step_id": "wait",
        "type": "wait_until",
        "wait_until": {"resume_at": past},
    }]
    err = _validate_wait_until_steps_for_production(_Comp({}, steps))
    assert err is not None


def test_wait_until_validator_ignores_non_wait_steps():
    steps = [
        {"step_id": "1", "type": "tool", "tool": "noop"},
        {"step_id": "2", "type": "elicit", "elicit": {"message": "ok?", "schema": {"type": "object"}}},
    ]
    assert _validate_wait_until_steps_for_production(_Comp({}, steps)) is None


# ---------------------------------------------------------------------------
# B-1.3: subcomposition step validation at promote time
# ---------------------------------------------------------------------------

# These tests need a DB session because the validator queries the
# target composition. They follow the same fixture pattern as the
# other B-1 test files.

import asyncio
from uuid import UUID, uuid4

import pytest as _pytest
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

from app.models.composition import (
    Composition as _Composition,
    CompositionStatus as _CompositionStatus,
    CompositionVisibility as _CompositionVisibility,
)
from app.models.organization import OrganizationMember as _OrgMember
from app.models.user import User as _User
from app.services.composition_service import (
    _validate_subcomposition_steps_for_production,
)


_subpytestmark = _pytest.mark.asyncio


async def _sub_ids(db: _AsyncSession, email: str):
    user = (await db.execute(_select(_User).where(_User.email == email))).scalar_one()
    member = (
        await db.execute(
            _select(_OrgMember).where(_OrgMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _sub_make(db, org_id, owner_id, *, name, steps, status=_CompositionStatus.PRODUCTION):
    comp = _Composition(
        organization_id=org_id,
        created_by=owner_id,
        name=name,
        description="b1.3 promote validation",
        visibility=_CompositionVisibility.PRIVATE.value,
        steps=steps,
        data_mappings=[],
        input_schema={"type": "object", "properties": {}, "required": []},
        output_schema=None,
        server_bindings={},
        allowed_roles=[],
        force_org_credentials=False,
        status=status.value,
        ttl=None,
        extra_metadata={},
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return comp


@_pytest.mark.asyncio
async def test_subcomposition_valid_target_passes(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    target = await _sub_make(
        db_session, org_id, user_id, name="b1_v_target",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
    )
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_parent",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(target.id)},
        }],
    )
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is None


@_pytest.mark.asyncio
async def test_subcomposition_missing_composition_id_rejected(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_missing_id",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {},
        }],
    )
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is not None
    assert "composition_id" in err


@_pytest.mark.asyncio
async def test_subcomposition_unknown_target_rejected(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_unknown",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(uuid4())},
        }],
    )
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is not None
    assert "does not exist" in err


@_pytest.mark.asyncio
async def test_subcomposition_self_reference_rejected(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    # Make a parent that will reference its own ID
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_self",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
    )
    parent.steps = [{
        "step_id": "call",
        "type": "subcomposition",
        "subcomposition": {"composition_id": str(parent.id)},
    }]
    await db_session.commit()
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is not None
    assert "self-reference" in err


@_pytest.mark.asyncio
async def test_subcomposition_non_production_target_rejected(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    target = await _sub_make(
        db_session, org_id, user_id, name="b1_v_draft",
        steps=[{"step_id": "1", "type": "tool", "tool": "noop"}],
        status=_CompositionStatus.TEMPORARY,
    )
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_parent_draft",
        steps=[{
            "step_id": "call",
            "type": "subcomposition",
            "subcomposition": {"composition_id": str(target.id)},
        }],
    )
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is not None
    assert "production" in err.lower()


@_pytest.mark.asyncio
async def test_subcomposition_validator_ignores_non_subcomp_steps(
    db_session: _AsyncSession, test_user: dict
):
    user_id, org_id = await _sub_ids(db_session, test_user["email"])
    parent = await _sub_make(
        db_session, org_id, user_id, name="b1_v_other",
        steps=[
            {"step_id": "1", "type": "tool", "tool": "noop"},
            {"step_id": "2", "type": "_test_suspend"},
        ],
    )
    err = await _validate_subcomposition_steps_for_production(db_session, parent)
    assert err is None
