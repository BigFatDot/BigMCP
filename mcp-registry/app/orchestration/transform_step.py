"""`transform` step type — LLM-backed structured extraction.

Bridges tools that return unstructured prose (e.g. the data.gouv.fr MCP
server, whose tools return a single `structuredContent.result` string) into
the composition data-flow. A transform step takes a `source` (resolved via the
usual ${step_N...} reference) plus an `output_schema` (JSON Schema), asks the
LLM to extract a conforming object, validates it, and returns it as the step
result — so downstream steps can navigate ${step_Nb.field.path}.

Non-suspending: runs synchronously like a `tool` step. NOT a member of
SUSPENDING_STEP_TYPES.

Step shape:
    {
      "step_id": "1b",
      "type": "transform",
      "source": "${step_1.structuredContent.result}",
      "instruction": "Extract publishing organizations",   # optional
      "output_schema": { ...JSON Schema (object)... }
    }
"""

import json
import logging
from typing import Any, Dict

from jsonschema import Draft7Validator, ValidationError

from .llm_client import call_llm_json

logger = logging.getLogger(__name__)


class TransformConfigError(ValueError):
    """Raised when a transform step is misconfigured (caught at promote time)."""


def validate_config(step: Dict[str, Any]) -> None:
    """Validate a transform step's static config. Raises TransformConfigError.

    Checked at promote time so production compositions can't ship a transform
    step that would fail at run time.
    """
    if not step.get("source"):
        raise TransformConfigError(
            f"transform step {step.get('step_id')!r} requires a non-empty 'source'"
        )
    schema = step.get("output_schema")
    if not isinstance(schema, dict) or not schema:
        raise TransformConfigError(
            f"transform step {step.get('step_id')!r} requires a non-empty "
            f"'output_schema' (JSON Schema object)"
        )
    # Confirm it's a usable JSON Schema.
    try:
        Draft7Validator.check_schema(schema)
    except Exception as e:  # jsonschema.SchemaError
        raise TransformConfigError(
            f"transform step {step.get('step_id')!r} has an invalid output_schema: {e}"
        )


def _build_prompt(source_text: str, schema: Dict[str, Any], instruction: str) -> str:
    parts = [
        "Extract structured data from the SOURCE text below into a JSON object "
        "that strictly conforms to the TARGET SCHEMA.",
    ]
    if instruction:
        parts.append(f"\nExtraction goal: {instruction}")
    parts.append(
        "\nRules:\n"
        "- Output ONLY the JSON object, no prose, no markdown fences.\n"
        "- Include every field the schema marks required.\n"
        "- If the source has no value for an optional field, omit it.\n"
        "- Do not invent values that are not present in the source."
    )
    parts.append("\nTARGET SCHEMA:\n" + json.dumps(schema, ensure_ascii=False))
    parts.append("\nSOURCE:\n" + source_text)
    return "\n".join(parts)


async def execute(step: Dict[str, Any], resolved_source: Any, *, max_attempts: int = 2) -> Dict[str, Any]:
    """Run the LLM extraction for a transform step.

    `resolved_source` is the already-resolved value of step['source'] (the
    caller resolves ${...} references first). Returns the validated structured
    object. Raises on misconfiguration, LLM failure, or persistent schema
    non-conformance.
    """
    validate_config(step)
    schema = step["output_schema"]
    instruction = step.get("instruction", "") or ""

    if isinstance(resolved_source, str):
        source_text = resolved_source
    else:
        source_text = json.dumps(resolved_source, ensure_ascii=False, default=str)

    if not source_text or not source_text.strip():
        raise ValueError(
            f"transform step {step.get('step_id')!r}: resolved source is empty"
        )

    system = (
        "You are a precise data-extraction function. You convert unstructured "
        "text into JSON that conforms to a provided JSON Schema. You never add "
        "commentary."
    )
    prompt = _build_prompt(source_text, schema, instruction)
    validator = Draft7Validator(schema)

    last_error: str = "unknown"
    for attempt in range(1, max_attempts + 1):
        result = await call_llm_json(prompt, system=system)
        errors = sorted(validator.iter_errors(result), key=lambda e: e.path)
        if not errors:
            logger.info(
                f"transform step {step.get('step_id')!r} produced conforming "
                f"output on attempt {attempt}"
            )
            return result
        last_error = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors[:5]
        )
        logger.warning(
            f"transform step {step.get('step_id')!r} output failed schema "
            f"validation (attempt {attempt}/{max_attempts}): {last_error}"
        )
        prompt = (
            _build_prompt(source_text, schema, instruction)
            + f"\n\nYour previous output failed schema validation: {last_error}. "
            "Return corrected JSON that conforms exactly."
        )

    raise ValueError(
        f"transform step {step.get('step_id')!r}: LLM output did not conform to "
        f"output_schema after {max_attempts} attempts ({last_error})"
    )
