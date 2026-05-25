"""Tests for _extract_value_smart — the tool/transform reference asymmetry.

Tool results wrap payload under `structuredContent`; transform/foreach results
are naked dicts. References must resolve regardless of which convention the
author/LLM used, so chaining transform->transform (or tool->transform) doesn't
silently yield empty values.
"""

from app.orchestration.composition_executor import CompositionExecutor

_S = CompositionExecutor(registry=None)._extract_value_smart


def test_transform_naked_direct():
    assert _S({"datasets": [{"id": "a"}]}, "datasets[0].id") == "a"


def test_tool_payload_referenced_without_prefix():
    # tool result (payload under structuredContent) referenced transform-style
    assert _S(
        {"structuredContent": {"datasets": [{"id": "b"}]}, "isError": False},
        "datasets[0].id",
    ) == "b"


def test_transform_referenced_with_wrong_structuredcontent_prefix():
    # transform output (naked) referenced tool-style — the bug that zeroed the
    # final aggregation step
    assert _S({"datasets": [{"id": "c"}]}, "structuredContent.datasets[0].id") == "c"


def test_tool_raw_prose_correct_prefix():
    assert _S({"structuredContent": {"result": "hello"}}, "structuredContent.result") == "hello"


def test_wildcard_across_asymmetry_naked_with_prefix():
    assert _S(
        {"datasets": [{"resource_count": 8}, {"resource_count": 92}]},
        "structuredContent.datasets[*].resource_count",
    ) == [8, 92]


def test_wildcard_across_asymmetry_wrapped_without_prefix():
    assert _S(
        {"structuredContent": {"datasets": [{"resource_count": 8}, {"resource_count": 92}]}},
        "datasets[*].resource_count",
    ) == [8, 92]


def test_returns_none_when_truly_absent():
    assert _S({"datasets": [{"id": "a"}]}, "organizations[0].id") is None
