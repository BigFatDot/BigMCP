"""``approval`` step type — Phase B-1.4.

Cross-user elicitation: composition A pauses; user X (≠ the launcher)
approves or rejects via a dedicated REST flow. The approver
permission is declared per-step (specific user_ids and/or roles) and
checked at the resume site by inverting the standard owner-only
``_load_owned_or_404`` gate.

Design highlights — reuse vs. new code:

REUSED VERBATIM from elicit (B-1.0):
- ``coerce_ttl``  — same TTL contract (1s … 24h, default 5min). Heavy
  approval workflows that need longer TTL should split into multiple
  steps or use cron triggers.
- ``resolve_message`` — prompt substitutions at SUSPEND time so the
  approver sees the same question the author wrote with the
  inputs/prior-step values frozen in.
- ``validate_response`` — JSON Schema validation of additional fields
  the author wants on the approval form (e.g., a free-text rationale).

NEW for approval:
- Two-arm approval permission: ``approver_user_ids`` (specific users)
  OR ``allowed_roles`` (Owner/Admin/Member by org membership). At
  least one of the two must be set; both can be combined (OR
  semantics — match either).
- Four-eyes default: the launcher's own user_id is implicitly
  excluded from approver_user_ids and role-based matches UNLESS
  ``allow_self_approval=true`` is set explicitly.
- Two terminal decisions: ``approved`` / ``rejected``. Both inject
  the response envelope into the step result; the executor's
  ``step.optional`` flag is what decides whether ``rejected``
  fails the composition or merely advances.

The endpoint surface ships in chunk 2: ``POST /executions/{id}/approve``,
``POST /executions/{id}/reject``, ``GET /executions/pending-approvals``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from .elicit_step import (
    coerce_ttl,
    resolve_message,
    validate_response as _validate_extra_fields,
)
from .execution_state import ExecutionState, Suspend


logger = logging.getLogger("orchestration.approval_step")


# Known role identifiers — match the OrganizationMember.role enum
# values (lowercased). Author config rejects anything else.
_VALID_ROLES: frozenset[str] = frozenset({"owner", "admin", "member", "viewer"})


class ApprovalConfigError(ValueError):
    """Author-supplied ``step.approval`` config is malformed."""


# ---------------------------------------------------------------------------
# Static author-config validation
# ---------------------------------------------------------------------------


def _normalise_role_list(raw: Any, *, field_name: str) -> List[str]:
    """Lowercase + dedup + validate against the known role set."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ApprovalConfigError(
            f"approval.{field_name} must be a list of role names "
            f"(got {type(raw).__name__})"
        )
    out: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ApprovalConfigError(
                f"approval.{field_name} entries must be strings, got "
                f"{type(item).__name__}"
            )
        lower = item.strip().lower()
        if not lower:
            continue
        if lower not in _VALID_ROLES:
            raise ApprovalConfigError(
                f"approval.{field_name} contains unknown role {item!r}; "
                f"valid roles: {sorted(_VALID_ROLES)}"
            )
        if lower in seen:
            continue
        seen.add(lower)
        out.append(lower)
    return out


def _normalise_user_id_list(raw: Any) -> List[str]:
    """Validate UUID-shape; return canonical lowercase string form."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ApprovalConfigError(
            f"approval.approver_user_ids must be a list of UUIDs "
            f"(got {type(raw).__name__})"
        )
    out: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ApprovalConfigError(
                f"approval.approver_user_ids entries must be UUID "
                f"strings, got {type(item).__name__}"
            )
        try:
            normalised = str(UUID(item))
        except (ValueError, TypeError):
            raise ApprovalConfigError(
                f"approval.approver_user_ids contains invalid UUID: "
                f"{item!r}"
            )
        if normalised in seen:
            continue
        seen.add(normalised)
        out.append(normalised)
    return out


def validate_config(approval: Optional[Dict[str, Any]]) -> None:
    """Validate the static author-supplied ``step.approval`` block.

    Raises :class:`ApprovalConfigError`. Author-required fields:
    - ``message``: non-empty string (supports substitutions).
    - At least one of ``approver_user_ids`` OR ``allowed_roles``.

    Optional:
    - ``response_schema``: JSON Schema for additional fields on the
      approval form (rationale, ticket number, …). The ``decision``
      key is always implicit; never declared in this schema.
    - ``ttl_seconds``: 1-86400 (default 300).
    - ``allow_self_approval``: bool, default false. When false, the
      launcher's own user_id cannot match the approver gate.
    """
    if not isinstance(approval, dict):
        raise ApprovalConfigError(
            "approval step requires an 'approval' object on the step "
            f"definition; got {type(approval).__name__}"
        )

    message = approval.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ApprovalConfigError(
            "approval.message must be a non-empty string"
        )

    approver_user_ids = _normalise_user_id_list(
        approval.get("approver_user_ids")
    )
    allowed_roles = _normalise_role_list(
        approval.get("allowed_roles"), field_name="allowed_roles"
    )
    if not approver_user_ids and not allowed_roles:
        raise ApprovalConfigError(
            "approval requires at least one of 'approver_user_ids' "
            "or 'allowed_roles' so the executor can resolve who is "
            "allowed to approve"
        )

    response_schema = approval.get("response_schema")
    if response_schema is not None:
        if not isinstance(response_schema, dict):
            raise ApprovalConfigError(
                "approval.response_schema must be a JSON Schema object "
                "or null"
            )
        if response_schema.get("type") is None:
            raise ApprovalConfigError(
                "approval.response_schema must declare a top-level 'type'"
            )

    allow_self = approval.get("allow_self_approval")
    if allow_self is not None and not isinstance(allow_self, bool):
        raise ApprovalConfigError(
            "approval.allow_self_approval must be a boolean"
        )

    coerce_ttl(approval.get("ttl_seconds"))


# ---------------------------------------------------------------------------
# Suspend builder — called by the executor's dispatch branch
# ---------------------------------------------------------------------------


def build_suspend(
    step: Dict[str, Any],
    state: ExecutionState,
    *,
    launcher_user_id: UUID,
) -> Suspend:
    """Materialise the Suspend payload for an ``approval`` step.

    Resolves the prompt now (the question approvers see is what the
    author wrote with substitutions frozen). Persists the approver
    gate (user_ids + roles) so the REST endpoint can authorise the
    incoming request without re-running this logic.

    The launcher's user_id is stored so the endpoint can enforce the
    four-eyes rule (default — denies self-approval).
    """
    approval = step.get("approval") or {}
    validate_config(approval)

    resolved_message = resolve_message(approval["message"], state)
    ttl = coerce_ttl(approval.get("ttl_seconds"))

    payload: Dict[str, Any] = {
        "step_id": step.get("step_id") or step.get("id"),
        "message": resolved_message,
        "approver_user_ids": _normalise_user_id_list(
            approval.get("approver_user_ids")
        ),
        "allowed_roles": _normalise_role_list(
            approval.get("allowed_roles"), field_name="allowed_roles"
        ),
        "launcher_user_id": str(launcher_user_id),
        "allow_self_approval": bool(approval.get("allow_self_approval", False)),
    }
    response_schema = approval.get("response_schema")
    if response_schema is not None:
        payload["response_schema"] = response_schema

    return Suspend(
        reason="approval",
        payload=payload,
        ttl_seconds=ttl,
    )


# ---------------------------------------------------------------------------
# Approver permission check — used by the REST endpoint
# ---------------------------------------------------------------------------


def can_approve(
    suspension_payload: Dict[str, Any],
    *,
    actor_user_id: UUID,
    actor_role: str,
) -> Tuple[bool, Optional[str]]:
    """Authorise an incoming approval/rejection.

    The actor's org membership has been verified upstream — same-org
    rule is enforced by the REST endpoint via ``OrganizationMember``
    lookup, not here.

    Returns ``(True, None)`` on success, ``(False, reason)`` on
    denial. The reason is for logs only — the REST endpoint surfaces
    a uniform 403 to avoid telling probers WHICH gate failed.
    """
    actor_id_str = str(actor_user_id)
    launcher = (suspension_payload or {}).get("launcher_user_id")
    if not (suspension_payload or {}).get("allow_self_approval", False):
        if launcher and actor_id_str == str(launcher):
            return False, "self_approval_disallowed"

    approver_ids = (suspension_payload or {}).get("approver_user_ids") or []
    if actor_id_str in {str(x) for x in approver_ids}:
        return True, None

    allowed_roles = (suspension_payload or {}).get("allowed_roles") or []
    role_lower = (actor_role or "").strip().lower()
    if role_lower and role_lower in {str(r).lower() for r in allowed_roles}:
        return True, None

    return False, "not_in_approver_set"


# ---------------------------------------------------------------------------
# Response envelope — what the executor.resume(...) receives
# ---------------------------------------------------------------------------


def build_response_envelope(
    *,
    decision: str,
    actor_user_id: UUID,
    suspension_payload: Dict[str, Any],
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the JSON the executor injects into the step result.

    Always includes:
    - ``decision``: ``approved`` | ``rejected`` (server-set, never
      user-controlled — the endpoint picks the value)
    - ``approved_by``: UUID of the actor (server-set from JWT)
    - ``approved_at``: ISO 8601 timestamp (server-set from clock)

    Plus whatever ``extra_fields`` validate against
    ``response_schema``.

    Author-controlled keys CANNOT shadow the server-set ones — if the
    schema declares ``approved_by``, we still overwrite it with the
    JWT value (the schema is meant for the rationale/ticket-id shape,
    not for spoofing the actor).
    """
    out: Dict[str, Any] = {}
    if extra_fields:
        for k, v in extra_fields.items():
            if k in {"decision", "approved_by", "approved_at"}:
                continue
            out[k] = v
    out["decision"] = decision
    out["approved_by"] = str(actor_user_id)
    out["approved_at"] = datetime.utcnow().isoformat() + "Z"
    return out


def validate_response_schema(
    suspension_payload: Dict[str, Any],
    extra_fields: Any,
) -> Tuple[bool, Optional[str]]:
    """Validate the author-declared response_schema against
    ``extra_fields`` (the body keys other than ``decision``)."""
    schema = (suspension_payload or {}).get("response_schema")
    if schema is None:
        return True, None
    return _validate_extra_fields({"schema": schema}, extra_fields or {})
