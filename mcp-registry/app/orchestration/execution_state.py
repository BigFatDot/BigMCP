"""Composition execution state — the shape of ``CompositionExecution.state``.

The state JSONB carries everything needed to resume an execution from
where it left off. Keeping it in a typed dataclass (rather than naked
dicts everywhere) makes the executor logic easier to reason about
and prevents typo bugs.

Persisted shape (round-trips through ``to_jsonb`` / ``from_jsonb``):

    {
      "step_results":     { step_id: <result-value> },
      "step_status":      { step_id: "pending"|"in_progress"|"succeeded"|"failed" },
      "step_started_at":  { step_id: ISO8601 string },
      "current_step_id":  str | None,         # the step that suspended (if any)
      "suspension":       { reason, payload, ttl_seconds } | None,
      "depth":            int                  # sub-composition nesting (0 = root)
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


StepStatus = Literal["pending", "in_progress", "succeeded", "failed"]


@dataclass
class Suspend:
    """Signal returned by ``_execute_step`` to pause an execution.

    The reason names a logical category (``_test_suspend`` in B-0;
    ``elicit``, ``wait_callback``, ``wait_until``, ``approval``,
    ``subcomposition`` in B-1+). The ``payload`` is opaque to the
    state machine — its shape is defined by whoever resumes
    (UI modal for elicit, webhook for wait_callback, scheduler for
    wait_until, etc.).
    """

    reason: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: int = 300

    def to_jsonb(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "payload": self.payload,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class ExecutionState:
    """Mirror of ``CompositionExecution.state`` JSONB with helpers."""

    step_results: Dict[str, Any] = field(default_factory=dict)
    step_status: Dict[str, str] = field(default_factory=dict)
    step_started_at: Dict[str, str] = field(default_factory=dict)
    current_step_id: Optional[str] = None
    suspension: Optional[Dict[str, Any]] = None
    depth: int = 0

    @classmethod
    def from_jsonb(cls, blob: Optional[Dict[str, Any]]) -> "ExecutionState":
        if not blob:
            return cls()
        return cls(
            step_results=blob.get("step_results") or {},
            step_status=blob.get("step_status") or {},
            step_started_at=blob.get("step_started_at") or {},
            current_step_id=blob.get("current_step_id"),
            suspension=blob.get("suspension"),
            depth=int(blob.get("depth") or 0),
        )

    def to_jsonb(self) -> Dict[str, Any]:
        return {
            "step_results": self.step_results,
            "step_status": self.step_status,
            "step_started_at": self.step_started_at,
            "current_step_id": self.current_step_id,
            "suspension": self.suspension,
            "depth": self.depth,
        }
