"""Phase B-1.5: ``wait_callback`` step type — token gen + validate + dispatch.

Endpoint-level tests (POST .../callback/{token}) live in
test_wait_callback_endpoint_b1.py to keep the unit-level surface
isolated from the HTTP/JWT plumbing.
"""

from __future__ import annotations

import hashlib
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
from app.orchestration.composition_routing import SUSPENDING_STEP_TYPES
from app.orchestration.execution_state import ExecutionState
from app.orchestration.resumable_executor import (
    create_execution,
    get_executor,
    _reset_executor_for_tests,
)
from app.orchestration.wait_callback_step import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    WaitCallbackConfigError,
    build_callback_url,
    build_suspend,
    compare_token,
    coerce_ttl,
    validate_callback,
    validate_config,
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
        description="b1.5 wait_callback",
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


def test_wait_callback_in_suspending_step_types():
    assert "wait_callback" in SUSPENDING_STEP_TYPES


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_validate_config_accepts_none():
    validate_config(None)  # author wants defaults


def test_validate_config_accepts_empty_dict():
    validate_config({})


def test_validate_config_rejects_non_dict():
    with pytest.raises(WaitCallbackConfigError):
        validate_config("oops")


def test_validate_config_rejects_non_dict_schema():
    with pytest.raises(WaitCallbackConfigError):
        validate_config({"expected_schema": "not-a-dict"})


def test_validate_config_accepts_schema():
    validate_config({"expected_schema": {"type": "object"}})


def test_coerce_ttl_defaults():
    assert coerce_ttl(None) == DEFAULT_TTL_SECONDS


def test_coerce_ttl_rejects_out_of_range():
    with pytest.raises(WaitCallbackConfigError):
        coerce_ttl(0)
    with pytest.raises(WaitCallbackConfigError):
        coerce_ttl(MAX_TTL_SECONDS + 1)


def test_coerce_ttl_rejects_non_int():
    with pytest.raises(WaitCallbackConfigError):
        coerce_ttl("60")
    with pytest.raises(WaitCallbackConfigError):
        coerce_ttl(60.5)


# ---------------------------------------------------------------------------
# Token + URL helpers
# ---------------------------------------------------------------------------


def test_compare_token_constant_time_accept():
    token = "the-real-token"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert compare_token(token, digest) is True


def test_compare_token_rejects_wrong_token():
    digest = hashlib.sha256(b"abc").hexdigest()
    assert compare_token("def", digest) is False


def test_compare_token_handles_non_strings():
    digest = hashlib.sha256(b"abc").hexdigest()
    assert compare_token(None, digest) is False
    assert compare_token("abc", None) is False


def test_build_callback_url_uses_env_when_set(monkeypatch):
    monkeypatch.setenv("CALLBACK_BASE_URL", "https://my-instance.example.com/")
    exec_id = uuid4()
    url = build_callback_url(exec_id, "tok123")
    assert url.startswith("https://my-instance.example.com/")
    assert str(exec_id) in url
    assert "tok123" in url


def test_build_callback_url_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("CALLBACK_BASE_URL", raising=False)
    exec_id = uuid4()
    url = build_callback_url(exec_id, "tok123")
    assert url.startswith("/api/v1/compositions/executions/")
    assert "tok123" in url


# ---------------------------------------------------------------------------
# Validate callback (token check + optional schema)
# ---------------------------------------------------------------------------


def test_validate_callback_accepts_matching_token():
    token = "secret"
    digest = hashlib.sha256(token.encode()).hexdigest()
    ok, err = validate_callback({"token_hash": digest}, token, {"any": "body"})
    assert ok is True
    assert err is None


def test_validate_callback_rejects_bad_token():
    digest = hashlib.sha256(b"x").hexdigest()
    ok, err = validate_callback({"token_hash": digest}, "y", {})
    assert ok is False
    assert err == "invalid token"


def test_validate_callback_rejects_missing_hash():
    ok, err = validate_callback({}, "anything", {})
    assert ok is False


def test_validate_callback_validates_body_when_schema_set():
    token = "ok"
    digest = hashlib.sha256(token.encode()).hexdigest()
    payload = {
        "token_hash": digest,
        "expected_schema": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    }
    ok, err = validate_callback(payload, token, {})  # missing required
    assert ok is False
    assert "status" in (err or "")


def test_validate_callback_passes_body_when_schema_satisfied():
    token = "ok"
    digest = hashlib.sha256(token.encode()).hexdigest()
    payload = {
        "token_hash": digest,
        "expected_schema": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    }
    ok, err = validate_callback(payload, token, {"status": "done"})
    assert ok is True
    assert err is None


# ---------------------------------------------------------------------------
# build_suspend
# ---------------------------------------------------------------------------


def test_build_suspend_includes_url_and_hash():
    step = {
        "step_id": "cb",
        "type": "wait_callback",
        "wait_callback": {"ttl_seconds": 600},
    }
    state = ExecutionState()
    out = build_suspend(step, state, uuid4())
    assert out.reason == "wait_callback"
    assert out.ttl_seconds == 600
    assert out.payload["step_id"] == "cb"
    assert "token_hash" in out.payload
    assert "callback_url" in out.payload
    # Hash is 64 hex chars (SHA-256)
    assert len(out.payload["token_hash"]) == 64
    # Plain token from the URL must validate against the hash
    url = out.payload["callback_url"]
    token = url.rsplit("/", 1)[-1]
    assert compare_token(token, out.payload["token_hash"]) is True


def test_build_suspend_carries_expected_schema():
    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    step = {
        "step_id": "cb",
        "type": "wait_callback",
        "wait_callback": {"expected_schema": schema},
    }
    out = build_suspend(step, ExecutionState(), uuid4())
    assert out.payload["expected_schema"] == schema


def test_build_suspend_defaults_when_no_config():
    step = {"step_id": "cb", "type": "wait_callback"}
    out = build_suspend(step, ExecutionState(), uuid4())
    assert out.ttl_seconds == DEFAULT_TTL_SECONDS
    assert "expected_schema" not in out.payload


# ---------------------------------------------------------------------------
# End-to-end via the executor
# ---------------------------------------------------------------------------


async def test_executor_yields_with_callback_url(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_callback_yield",
        steps=[{
            "step_id": "wh",
            "type": "wait_callback",
            "wait_callback": {"ttl_seconds": 300},
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
    assert susp.get("reason") == "wait_callback"
    payload = susp.get("payload") or {}
    assert payload.get("step_id") == "wh"
    assert "callback_url" in payload
    assert "token_hash" in payload
    # URL contains the execution id
    assert str(eid) in payload["callback_url"]


async def test_executor_resume_completes_with_body_payload(
    db_session: AsyncSession, test_user: dict
):
    """Direct executor.resume (bypass the endpoint) injects the body
    as the step result, just like the REST callback would."""
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = await _make_composition(
        db_session, org_id, user_id, name="b1_callback_round_trip",
        steps=[{
            "step_id": "wh",
            "type": "wait_callback",
        }],
    )
    eid = await create_execution(
        composition_id=comp.id, user_id=user_id, organization_id=org_id,
        trigger="manual",
    )
    executor = get_executor()
    await executor.run(eid)

    body = {"job_id": "abc", "status": "complete"}
    final = await executor.resume(eid, body)
    assert final == ExecutionStatus.COMPLETED.value

    row = await db_session.get(CompositionExecution, eid)
    await db_session.refresh(row)
    assert row.state["step_results"]["wh"] == body
