"""``wait_until`` step type — Phase B-1.2.

Clock-driven suspension. The author declares either a relative wait
(``wait_seconds: 300``) or an absolute resume time
(``resume_at: "2026-05-16T12:00:00Z"``); the executor yields a
``Suspend`` whose ``expires_at`` doubles as the FIRE time. A periodic
scanner in ``queue_worker.py`` queries suspended rows whose
``expires_at`` has passed and, for ``wait_until``, calls
``executor.resume(id, {"resumed_at": <iso>})`` to continue the
composition.

This is the simplest production step type — no human, no external
HTTP, just the clock. Unblocks "schedule a follow-up after N minutes"
patterns without waiting for B-2 cron triggers.

Design highlights:
- ``wait_seconds`` and ``resume_at`` are mutually exclusive. Authors
  pick one; the other is computed.
- Hard cap on the wait: 30 days (2_592_000s). Longer waits should
  use ``wait_callback`` (B-1.5) so an external event drives the
  resume, not a long-lived suspended row.
- The resume payload is ``{"resumed_at": <iso>}`` — useful for steps
  that need to know when they actually fired (clock skew, scheduler
  lag).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .execution_state import ExecutionState, Suspend


logger = logging.getLogger("orchestration.wait_until_step")


# 30 days. Longer waits leak resources (the row is held suspended)
# and should instead be modelled as an external callback.
MAX_WAIT_SECONDS = 30 * 24 * 3600
MIN_WAIT_SECONDS = 1


class WaitUntilConfigError(ValueError):
    """Author-supplied ``step.wait_until`` config is malformed."""


# ---------------------------------------------------------------------------
# Author config validation
# ---------------------------------------------------------------------------


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 string into a naive UTC datetime.

    Mirrors the convention used elsewhere in the executor (``datetime.utcnow()``
    everywhere → naive UTC). Accepts trailing ``Z``.
    """
    if not isinstance(value, str):
        raise WaitUntilConfigError(
            f"wait_until.resume_at must be an ISO 8601 string, got {type(value).__name__}"
        )
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as e:
        raise WaitUntilConfigError(
            f"wait_until.resume_at is not valid ISO 8601: {value!r} ({e})"
        )
    if parsed.tzinfo is None:
        # Author wrote a naive value — assume UTC.
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def validate_config(wait_until: Optional[Dict[str, Any]]) -> None:
    """Validate the static author-supplied ``step.wait_until`` block.

    Raises WaitUntilConfigError for any structural issue. Promote
    validator delegates here; the executor calls it again on dispatch.
    """
    if not isinstance(wait_until, dict):
        raise WaitUntilConfigError(
            "wait_until step requires a 'wait_until' object on the step "
            f"definition; got {type(wait_until).__name__}"
        )

    has_seconds = "wait_seconds" in wait_until
    has_absolute = "resume_at" in wait_until
    if not has_seconds and not has_absolute:
        raise WaitUntilConfigError(
            "wait_until needs one of 'wait_seconds' or 'resume_at'"
        )
    if has_seconds and has_absolute:
        raise WaitUntilConfigError(
            "wait_until: 'wait_seconds' and 'resume_at' are mutually "
            "exclusive — pick one"
        )

    if has_seconds:
        secs = wait_until.get("wait_seconds")
        if isinstance(secs, bool) or not isinstance(secs, int):
            raise WaitUntilConfigError(
                f"wait_until.wait_seconds must be a positive integer, got "
                f"{secs!r}"
            )
        if secs < MIN_WAIT_SECONDS or secs > MAX_WAIT_SECONDS:
            raise WaitUntilConfigError(
                f"wait_until.wait_seconds must be in "
                f"[{MIN_WAIT_SECONDS}, {MAX_WAIT_SECONDS}] (30 days), "
                f"got {secs}. Longer waits belong to wait_callback."
            )
    else:
        # Absolute timestamp; ensure parseable AND in-range when
        # compared to now.
        target = _parse_iso(wait_until["resume_at"])
        delta = (target - datetime.utcnow()).total_seconds()
        if delta < MIN_WAIT_SECONDS:
            raise WaitUntilConfigError(
                f"wait_until.resume_at is in the past (or < {MIN_WAIT_SECONDS}s "
                f"away). Use a future timestamp."
            )
        if delta > MAX_WAIT_SECONDS:
            raise WaitUntilConfigError(
                f"wait_until.resume_at is > {MAX_WAIT_SECONDS}s away "
                f"(30 days). Longer waits belong to wait_callback."
            )


# ---------------------------------------------------------------------------
# Suspend builder
# ---------------------------------------------------------------------------


def compute_resume_at(wait_until: Dict[str, Any]) -> datetime:
    """Return the naive-UTC datetime when this wait should fire.

    Resolves the relative form into an absolute one. Validates input
    via ``validate_config`` so callers don't have to.
    """
    validate_config(wait_until)
    if "wait_seconds" in wait_until:
        return datetime.utcnow() + timedelta(seconds=int(wait_until["wait_seconds"]))
    return _parse_iso(wait_until["resume_at"])


def build_suspend(step: Dict[str, Any]) -> Suspend:
    """Materialise the Suspend payload for a ``wait_until`` step.

    The ``ttl_seconds`` on the returned Suspend doubles as the FIRE
    time — the executor stores ``expires_at = utcnow() + ttl_seconds``
    and the queue worker's expiry scanner uses that timestamp to
    decide when to resume (B-1.2 chunk 2).
    """
    wait_until = step.get("wait_until") or {}
    target = compute_resume_at(wait_until)
    delta = max(MIN_WAIT_SECONDS, int((target - datetime.utcnow()).total_seconds()))

    return Suspend(
        reason="wait_until",
        payload={
            "step_id": step.get("step_id") or step.get("id"),
            "resume_at": target.isoformat() + "Z",
            "wait_seconds_at_suspend": delta,
        },
        ttl_seconds=delta,
    )


# ---------------------------------------------------------------------------
# Auto-resume payload
# ---------------------------------------------------------------------------


def auto_resume_payload() -> Dict[str, Any]:
    """The body the expiry scanner injects when a wait_until fires.

    Authors get to know WHEN the wait actually completed (so they can
    detect scheduler lag, audit timing, etc.).
    """
    return {"resumed_at": datetime.utcnow().isoformat() + "Z"}
