"""Unit tests for the `transform` step type (LLM-backed structured extraction).

The LLM call itself is monkeypatched — these tests cover config validation,
schema-conformance enforcement, retry-on-nonconformance, and the failure
surface. They do NOT hit the network.
"""

import pytest

from app.orchestration import transform_step
from app.orchestration.transform_step import (
    TransformConfigError,
    validate_config,
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "organizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        }
    },
    "required": ["organizations"],
}


def _step(**over):
    base = {
        "step_id": "1b",
        "type": "transform",
        "source": "${step_1.structuredContent.result}",
        "output_schema": _SCHEMA,
    }
    base.update(over)
    return base


# --- validate_config ------------------------------------------------------


def test_validate_config_ok():
    validate_config(_step())  # no raise


def test_validate_config_missing_source():
    with pytest.raises(TransformConfigError):
        validate_config(_step(source=""))


def test_validate_config_missing_schema():
    with pytest.raises(TransformConfigError):
        validate_config(_step(output_schema={}))


def test_validate_config_invalid_schema():
    with pytest.raises(TransformConfigError):
        validate_config(_step(output_schema={"type": "not-a-real-type"}))


# --- execute --------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_returns_conforming_output(monkeypatch):
    async def fake_llm(prompt, system=None, **kw):
        return {"organizations": [{"id": "5c812a16"}]}

    monkeypatch.setattr(transform_step, "call_llm_json", fake_llm)
    out = await transform_step.execute(_step(), "Found 1 org... ID: 5c812a16")
    assert out == {"organizations": [{"id": "5c812a16"}]}


@pytest.mark.asyncio
async def test_execute_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def fake_llm(prompt, system=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"organizations": [{"wrong_field": "x"}]}  # missing required id
        return {"organizations": [{"id": "ok"}]}

    monkeypatch.setattr(transform_step, "call_llm_json", fake_llm)
    out = await transform_step.execute(_step(), "prose", max_attempts=2)
    assert out == {"organizations": [{"id": "ok"}]}
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_execute_fails_when_never_conforms(monkeypatch):
    async def fake_llm(prompt, system=None, **kw):
        return {"organizations": [{"wrong": 1}]}  # always invalid

    monkeypatch.setattr(transform_step, "call_llm_json", fake_llm)
    with pytest.raises(ValueError, match="did not conform"):
        await transform_step.execute(_step(), "prose", max_attempts=2)


@pytest.mark.asyncio
async def test_execute_rejects_empty_source(monkeypatch):
    async def fake_llm(prompt, system=None, **kw):  # pragma: no cover
        return {"organizations": []}

    monkeypatch.setattr(transform_step, "call_llm_json", fake_llm)
    with pytest.raises(ValueError, match="source is empty"):
        await transform_step.execute(_step(), "   ")


@pytest.mark.asyncio
async def test_execute_serializes_non_string_source(monkeypatch):
    seen = {}

    async def fake_llm(prompt, system=None, **kw):
        seen["prompt"] = prompt
        return {"organizations": [{"id": "x"}]}

    monkeypatch.setattr(transform_step, "call_llm_json", fake_llm)
    await transform_step.execute(_step(), {"raw": ["a", "b"]})
    assert '"raw"' in seen["prompt"]  # dict was JSON-encoded into the prompt
