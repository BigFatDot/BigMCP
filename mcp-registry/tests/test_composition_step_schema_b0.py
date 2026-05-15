"""Phase B-0 chunk 12: CompositionStep Pydantic schema canonical fields.

Validates the schema fix that aligns ``CompositionStep`` with the
runtime canonical names (``step_id`` / ``parameters``) and rejects
the legacy ``id`` / ``params`` aliases at parse time so authors get
a 422 instead of a silent runtime mismatch later.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.composition import CompositionStep


def test_canonical_fields_parse():
    step = CompositionStep(
        step_id="s1",
        tool="my_tool",
        parameters={"x": 1},
        depends_on=[],
    )
    assert step.step_id == "s1"
    assert step.tool == "my_tool"
    assert step.parameters == {"x": 1}
    assert step.type == "tool"  # default
    assert step.idempotent is False
    assert step.optional is False


def test_legacy_id_rejected_with_422():
    """``id`` is the legacy alias — must be rejected, not silently mapped."""
    with pytest.raises(ValidationError) as ei:
        CompositionStep(
            id="s1",  # legacy
            tool="t",
            parameters={},
        )
    # The error mentions either 'id' (extra forbidden) or step_id missing
    msg = str(ei.value)
    assert "id" in msg or "step_id" in msg


def test_legacy_params_rejected_with_422():
    """``params`` is the legacy alias — must be rejected."""
    with pytest.raises(ValidationError) as ei:
        CompositionStep(
            step_id="s1",
            tool="t",
            params={"x": 1},  # legacy
        )
    msg = str(ei.value)
    assert "params" in msg or "parameters" in msg


def test_unknown_extra_keys_rejected():
    """``extra='forbid'`` — unknown keys raise instead of being dropped."""
    with pytest.raises(ValidationError):
        CompositionStep(
            step_id="s1",
            tool="t",
            parameters={},
            unknown_field="oops",
        )


def test_type_accepts_any_string():
    """Forward-compatible: ``type`` is free-form; executor validates."""
    step = CompositionStep(
        step_id="s1",
        type="some_future_step_kind",
    )
    assert step.type == "some_future_step_kind"
    # Tool may be omitted for non-tool step types
    assert step.tool is None


def test_test_suspend_step_parses():
    """B-0 ships ``_test_suspend`` — must round-trip cleanly."""
    step = CompositionStep(
        step_id="s1",
        type="_test_suspend",
    )
    assert step.type == "_test_suspend"


def test_idempotent_and_cancellable_default_false():
    """Safety defaults: re-run + cancel mid-flight are opt-in."""
    step = CompositionStep(step_id="s1", tool="t")
    assert step.idempotent is False
    assert step.cancellable is False


def test_timeout_seconds_optional():
    step = CompositionStep(step_id="s1", tool="t")
    assert step.timeout_seconds is None
    step2 = CompositionStep(step_id="s2", tool="t", timeout_seconds=30)
    assert step2.timeout_seconds == 30


def test_step_id_is_required():
    with pytest.raises(ValidationError):
        CompositionStep(tool="t")


def test_dump_uses_canonical_names():
    """``model_dump`` MUST emit canonical names so the JSON written
    to ``Composition.steps`` matches what the executor reads."""
    step = CompositionStep(
        step_id="s1",
        tool="t",
        parameters={"k": "v"},
        idempotent=True,
    )
    blob = step.model_dump()
    assert "step_id" in blob
    assert "parameters" in blob
    assert "id" not in blob
    assert "params" not in blob
    assert blob["idempotent"] is True
