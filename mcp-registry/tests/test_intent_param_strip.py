"""Unit tests for IntentAnalyzer parameter sanitation.

The LLM is handed each tool's inputSchema but still invents plausible keys
(e.g. ``sort=-last_modified`` on a tool with no ``sort`` field). Strict MCP
servers reject those with HTTP 400, so we strip unknown keys before execution.
"""

from app.orchestration.intent_analyzer import IntentAnalyzer

_strip = IntentAnalyzer._strip_unknown_params


def test_strips_hallucinated_key_keeps_valid():
    step = {"step_id": 1, "parameters": {"query": "Cerema", "sort": "-last_modified"}}
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    dropped = _strip(step, schema)
    assert dropped == ["sort"]
    assert step["parameters"] == {"query": "Cerema"}


def test_additional_properties_true_keeps_extras():
    step = {"parameters": {"query": "x", "foo": 1}}
    schema = {"type": "object", "properties": {"query": {}}, "additionalProperties": True}
    assert _strip(step, schema) == []
    assert step["parameters"] == {"query": "x", "foo": 1}


def test_open_schema_no_properties_is_noop():
    step = {"parameters": {"anything": 1}}
    assert _strip(step, {"type": "object"}) == []
    assert step["parameters"] == {"anything": 1}


def test_all_valid_params_kept():
    step = {"parameters": {"query": "x", "page_size": 5}}
    schema = {"properties": {"query": {}, "page_size": {}}}
    assert _strip(step, schema) == []


def test_empty_and_non_dict_params():
    assert _strip({"parameters": {}}, {"properties": {"a": {}}}) == []
    assert _strip({}, {"properties": {"a": {}}}) == []
    assert _strip({"parameters": "notadict"}, {"properties": {"a": {}}}) == []
