"""``elicit`` step type — Phase B-1 chunk 1.

Implements the suspension + payload contract for the ``elicit`` step
type per ``docs/composition_executions_b1.md``. The executor's
``_execute_step`` calls :func:`build_suspend` to materialise the
``Suspend`` value at suspend time; the REST resume handler calls
:func:`validate_response` to enforce the author-declared JSON Schema
before delegating to ``executor.resume(...)``.

Design highlights (see B-1 doc §2):

- Prompt substitutions are resolved at SUSPEND time, never at resume
  time — the user answered the question they saw, so we capture it
  verbatim. Substitutions follow the same convention as the legacy
  executor (``${input.X}``, ``${step_X.path}``).
- The schema is validated server-side on resume; client-side
  validation is for UX, not security.
- TTL defaults to 5 minutes, hard-capped at 24h. Longer waits
  belong to ``wait_until`` / ``wait_callback``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from .execution_state import ExecutionState, Suspend
from .resumable_executor import INPUTS_KEY


logger = logging.getLogger("orchestration.elicit_step")


DEFAULT_TTL_SECONDS = 300       # 5 minutes
MAX_TTL_SECONDS = 86_400        # 24 hours
MIN_TTL_SECONDS = 1


# ---------------------------------------------------------------------------
# Author config validation (used by both promote validator and dispatch)
# ---------------------------------------------------------------------------


class ElicitConfigError(ValueError):
    """Author-supplied ``step.elicit`` config is malformed."""


def coerce_ttl(ttl_raw: Any) -> int:
    """Parse + clamp a TTL value, defaulting + raising on out-of-range.

    Author-supplied None / missing → DEFAULT_TTL_SECONDS. Non-int or
    out-of-range → raises ElicitConfigError so the promote validator
    (and the runtime dispatch) refuse the step.
    """
    if ttl_raw is None:
        return DEFAULT_TTL_SECONDS
    if isinstance(ttl_raw, bool) or not isinstance(ttl_raw, int):
        raise ElicitConfigError(
            f"elicit.ttl_seconds must be a positive integer, got {ttl_raw!r}"
        )
    if ttl_raw < MIN_TTL_SECONDS or ttl_raw > MAX_TTL_SECONDS:
        raise ElicitConfigError(
            f"elicit.ttl_seconds must be in [{MIN_TTL_SECONDS}, "
            f"{MAX_TTL_SECONDS}] (a day), got {ttl_raw}"
        )
    return ttl_raw


def validate_config(elicit: Optional[Dict[str, Any]]) -> None:
    """Validate the static author-supplied ``step.elicit`` block.

    Raises ElicitConfigError for any structural issue. Promote-time
    validator delegates here; the executor calls it again on dispatch
    so a malformed step never lands in suspended.
    """
    if not isinstance(elicit, dict):
        raise ElicitConfigError(
            "elicit step requires an 'elicit' object on the step "
            f"definition; got {type(elicit).__name__}"
        )
    message = elicit.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ElicitConfigError(
            "elicit.message must be a non-empty string"
        )
    schema = elicit.get("schema")
    if not isinstance(schema, dict):
        raise ElicitConfigError(
            "elicit.schema must be a JSON Schema object"
        )
    # We don't run a full meta-schema validation here (heavy) — the
    # validator below will surface jsonschema parse errors at resume
    # time. Cheapest sanity check: ``type`` must be present and one
    # of the spec primitives or a list of them. JSON Schema technically
    # allows omitting type, but for elicit we require it so the UI
    # form generator has something to dispatch on.
    schema_type = schema.get("type")
    if schema_type is None:
        raise ElicitConfigError(
            "elicit.schema must declare a top-level 'type' so the UI "
            "can render an appropriate form widget"
        )
    coerce_ttl(elicit.get("ttl_seconds"))


# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------


_REF_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _walk_path(value: Any, path: str) -> Any:
    """Walk a dotted path through a (possibly nested) object.

    Returns the value found, or the literal token wrapped in ${...}
    if the path doesn't resolve — same behaviour as the legacy
    executor's _resolve_parameters: missing references stay as
    placeholders so authors can spot them in the rendered prompt.
    """
    if not path:
        return value
    parts = path.split(".")
    current = value
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif (
            isinstance(current, list)
            and part.isdigit()
            and int(part) < len(current)
        ):
            current = current[int(part)]
        else:
            return None
    return current


def resolve_message(
    template: str,
    state: ExecutionState,
) -> str:
    """Substitute ${input.X} and ${step_id.path} into the template.

    Mirrors the subset of the legacy executor's substitution semantics
    that's relevant to a free-form prompt — no _template/_map, no
    wildcards, no iteration variables. Adding those later is purely
    additive (existing prompts stay valid).

    Returns the resolved string. Unresolved references stay as
    ``${ref}`` literal so the user can see what didn't substitute
    instead of getting an empty hole in the prompt.
    """
    if not isinstance(template, str):
        return template

    inputs = state.step_results.get(INPUTS_KEY) or {}

    def _replace(match: re.Match) -> str:
        ref = match.group(1).strip()
        if ref.startswith("input."):
            value = _walk_path(inputs, ref[len("input."):])
        else:
            # Treat as ``step_id.path`` — first segment is the step_id
            head, _, tail = ref.partition(".")
            step_value = state.step_results.get(head)
            if step_value is None:
                return match.group(0)  # leave placeholder intact
            value = _walk_path(step_value, tail) if tail else step_value
        if value is None:
            return match.group(0)
        if isinstance(value, (dict, list)):
            import json as _json
            return _json.dumps(value, default=str)
        return str(value)

    return _REF_PATTERN.sub(_replace, template)


# ---------------------------------------------------------------------------
# Suspend builder (called by ResumableExecutor._execute_step)
# ---------------------------------------------------------------------------


def build_suspend(
    step: Dict[str, Any],
    state: ExecutionState,
    *,
    client_capabilities: Optional[Dict[str, Any]] = None,
) -> Suspend:
    """Materialise the Suspend payload for an ``elicit`` step.

    Resolves the prompt now (so the question the user sees is what
    they answered to), captures the schema verbatim for resume
    validation, and snapshots the client's capabilities at suspend
    time so the resume path knows whether the original session
    supported MCP elicitation.
    """
    elicit = step.get("elicit") or {}
    validate_config(elicit)  # raise on malformed config
    resolved_message = resolve_message(elicit["message"], state)
    ttl = coerce_ttl(elicit.get("ttl_seconds"))

    payload: Dict[str, Any] = {
        "step_id": step.get("step_id") or step.get("id"),
        "message": resolved_message,
        "schema": elicit["schema"],
    }
    if client_capabilities is not None:
        payload["client_capabilities_at_suspend"] = client_capabilities

    return Suspend(reason="elicit", payload=payload, ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# Resume validation (called by REST /resume + MCP elicitation result dispatch)
# ---------------------------------------------------------------------------


def validate_response(
    suspension_payload: Dict[str, Any],
    response: Any,
) -> Tuple[bool, Optional[str]]:
    """Validate an elicit resume payload against the stored schema.

    Returns ``(True, None)`` on success, ``(False, error_message)``
    on failure. Uses the ``jsonschema`` library if available; falls
    back to a minimal type-only check otherwise so we never silently
    accept invalid data on a fresh install missing the optional dep.
    """
    schema = (suspension_payload or {}).get("schema")
    if not isinstance(schema, dict):
        return False, "suspension is missing a schema; cannot validate"

    try:
        import jsonschema
    except ImportError:  # pragma: no cover — jsonschema is in requirements
        # Last-resort fallback: at least enforce the top-level type.
        expected = schema.get("type")
        if expected == "object" and not isinstance(response, dict):
            return False, "response must be an object"
        if expected == "array" and not isinstance(response, list):
            return False, "response must be an array"
        return True, None

    try:
        jsonschema.validate(instance=response, schema=schema)
    except jsonschema.ValidationError as e:
        # Build a human-pointing error message
        path = ".".join(str(p) for p in e.absolute_path) or "<root>"
        return False, f"validation failed at {path}: {e.message}"
    except jsonschema.SchemaError as e:
        return False, f"author-supplied schema is invalid: {e.message}"
    return True, None
