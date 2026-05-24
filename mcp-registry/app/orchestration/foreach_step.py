"""`foreach` step type — fan-out a sub-step over each item of a list.

Bridges the gap where a tool takes ONE value (e.g. get_metrics(dataset_id))
but the goal needs it run once per element of an array produced upstream
(e.g. "for each dataset, get its metrics"). The existing `_template/_map`
pattern only maps an array into a single call for tools that ACCEPT an array;
`foreach` issues N separate calls and aggregates their results.

Non-suspending: runs its iterations synchronously, like `tool`/`transform`.
NOT a member of SUSPENDING_STEP_TYPES.

Step shape:
    {
      "step_id": "3",
      "type": "foreach",
      "items": "${step_2b.datasets[*].id}",   # resolves to a list
      "do": {                                  # sub-step run per item
        "tool": "DataGouv__get_metrics",
        "parameters": {"dataset_id": "${_item}"}
      }
    }

Inside `do`, the current element is ${_item} and its index is ${_index}
(the same iteration variables _template/_map already supports).

Result: {"results": [...per-item result...], "count": N, "errors": [...]}.
Reference downstream as ${step_3.results[*]...}.
"""

from typing import Any, Dict

# Hard cap on iterations to keep a single foreach from issuing an unbounded
# number of tool calls (cost + latency runaway). Items beyond this are dropped
# and noted in the result.
MAX_ITEMS = 50


class ForeachConfigError(ValueError):
    """Raised when a foreach step is misconfigured (caught at promote time)."""


def validate_config(step: Dict[str, Any]) -> None:
    """Validate a foreach step's static config. Raises ForeachConfigError."""
    sid = step.get("step_id")
    if not step.get("items"):
        raise ForeachConfigError(
            f"foreach step {sid!r} requires an 'items' reference (e.g. "
            f"'${{step_N.field[*].id}}') that resolves to a list"
        )
    do = step.get("do")
    if not isinstance(do, dict) or not do:
        raise ForeachConfigError(
            f"foreach step {sid!r} requires a 'do' object describing the sub-step"
        )
    do_type = do.get("type", "tool")
    if do_type == "tool" and not do.get("tool"):
        raise ForeachConfigError(
            f"foreach step {sid!r}: 'do' tool sub-step requires a 'tool' field"
        )
    if do_type == "transform" and not do.get("source"):
        raise ForeachConfigError(
            f"foreach step {sid!r}: 'do' transform sub-step requires a 'source'"
        )
    if do_type not in ("tool", "transform"):
        raise ForeachConfigError(
            f"foreach step {sid!r}: 'do' type {do_type!r} unsupported "
            f"(use 'tool' or 'transform')"
        )
