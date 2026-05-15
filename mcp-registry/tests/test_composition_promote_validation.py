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
