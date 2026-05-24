"""Unit tests for the `foreach` step type.

config validation is pure; the execution loop is exercised against a stub
CompositionExecutor whose _execute_tool / _resolve_parameters are real (the
iteration-variable resolution is the part we care about), with the tool call
itself stubbed so no network/LLM is hit.
"""

import pytest

from app.orchestration import foreach_step
from app.orchestration.foreach_step import ForeachConfigError, validate_config
from app.orchestration.composition_executor import CompositionExecutor


def _step(**over):
    base = {
        "step_id": "3",
        "type": "foreach",
        "items": "${step_2.ids}",
        "do": {"tool": "Svc__get", "parameters": {"id": "${_item}"}},
    }
    base.update(over)
    return base


# --- validate_config ------------------------------------------------------


def test_validate_ok():
    validate_config(_step())


def test_validate_missing_items():
    with pytest.raises(ForeachConfigError):
        validate_config(_step(items=""))


def test_validate_missing_do():
    with pytest.raises(ForeachConfigError):
        validate_config(_step(do={}))


def test_validate_do_tool_without_tool_field():
    with pytest.raises(ForeachConfigError):
        validate_config(_step(do={"parameters": {}}))


def test_validate_do_bad_type():
    with pytest.raises(ForeachConfigError):
        validate_config(_step(do={"type": "elicit"}))


# --- execution ------------------------------------------------------------


@pytest.mark.asyncio
async def test_foreach_fans_out_over_items(monkeypatch):
    ex = CompositionExecutor(registry=None)
    calls = []

    async def fake_execute_tool(tool_name, params, context):
        calls.append((tool_name, params))
        return {"structuredContent": {"result": f"ok:{params['id']}"}}

    monkeypatch.setattr(ex, "_execute_tool", fake_execute_tool)

    context = {"step_results": {"2": {"ids": ["a", "b", "c"]}}, "parameters": {}}
    out = await ex._execute_foreach(_step(), context)

    assert out["count"] == 3
    assert out["errors"] == []
    assert [c[1]["id"] for c in calls] == ["a", "b", "c"]  # ${_item} per element


@pytest.mark.asyncio
async def test_foreach_collects_per_item_errors(monkeypatch):
    ex = CompositionExecutor(registry=None)

    async def fake_execute_tool(tool_name, params, context):
        if params["id"] == "b":
            # error-shaped prose (isError=false) must be counted as a failure
            return {"structuredContent": {"result": "Error: boom"}}
        return {"structuredContent": {"result": "ok"}}

    monkeypatch.setattr(ex, "_execute_tool", fake_execute_tool)
    context = {"step_results": {"2": {"ids": ["a", "b", "c"]}}, "parameters": {}}
    out = await ex._execute_foreach(_step(), context)

    assert out["count"] == 2
    assert len(out["errors"]) == 1
    assert out["errors"][0]["index"] == 1


@pytest.mark.asyncio
async def test_foreach_raises_when_all_fail(monkeypatch):
    ex = CompositionExecutor(registry=None)

    async def fake_execute_tool(tool_name, params, context):
        raise RuntimeError("nope")

    monkeypatch.setattr(ex, "_execute_tool", fake_execute_tool)
    context = {"step_results": {"2": {"ids": ["a", "b"]}}, "parameters": {}}
    with pytest.raises(ValueError, match="all 2 iteration"):
        await ex._execute_foreach(_step(), context)


@pytest.mark.asyncio
async def test_foreach_scalar_items_becomes_single_iteration(monkeypatch):
    ex = CompositionExecutor(registry=None)
    calls = []

    async def fake_execute_tool(tool_name, params, context):
        calls.append(params)
        return {"structuredContent": {"result": "ok"}}

    monkeypatch.setattr(ex, "_execute_tool", fake_execute_tool)
    # items resolves to a single scalar → treated as one-element list
    context = {"step_results": {"2": {"ids": "solo"}}, "parameters": {}}
    out = await ex._execute_foreach(_step(items="${step_2.ids}"), context)
    assert out["count"] == 1
    assert calls[0]["id"] == "solo"
