"""``wait_callback`` step type — Phase B-1.5.

Step suspends and exposes a per-execution per-step HMAC-protected
callback URL. An external system POSTs to that URL with a JSON body;
the endpoint validates the token in constant time, optionally
validates the body against an author-declared JSON Schema, and calls
``executor.resume(execution_id, body)`` to continue the composition.

Pattern: useful for any integration where you kick off an async
external job (a long-running pipeline, a video render, a third-party
batch import) and want the executor to pause until that system pings
us back. Avoids the polling / busy-wait shape entirely.

Security model:
- The plain token is generated server-side with ``secrets.token_urlsafe``
  (~256 bits of entropy). Only its SHA-256 hash lands in the DB
  alongside the suspension payload. Validation re-hashes the received
  token and compares with ``hmac.compare_digest``.
- The plain token also lives in the ``callback_url`` field of the
  suspension payload so the parent step (and any downstream steps)
  can pass it to the external system. The URL is server-built using
  ``CALLBACK_BASE_URL`` env (fallback to the request's base at
  endpoint time — useful for self-hosted with custom domains).
- TTL hard-capped at 24h. Webhooks should fire well within that;
  longer waits should orchestrate over multiple wait_callbacks or
  use cron triggers (B-2).
- The endpoint accepts the callback only while the row is
  ``suspended`` on ``reason='wait_callback'`` — a token replayed
  after success hits a 409.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from .execution_state import ExecutionState, Suspend


logger = logging.getLogger("orchestration.wait_callback_step")


DEFAULT_TTL_SECONDS = 24 * 3600          # 24 hours
MAX_TTL_SECONDS = 24 * 3600              # hard cap (longer → cron / multi-step)
MIN_TTL_SECONDS = 1
CALLBACK_PATH_TEMPLATE = "/api/v1/compositions/executions/{exec_id}/callback/{token}"


class WaitCallbackConfigError(ValueError):
    """Author-supplied ``step.wait_callback`` config is malformed."""


# ---------------------------------------------------------------------------
# Author config validation
# ---------------------------------------------------------------------------


def coerce_ttl(ttl_raw: Any) -> int:
    if ttl_raw is None:
        return DEFAULT_TTL_SECONDS
    if isinstance(ttl_raw, bool) or not isinstance(ttl_raw, int):
        raise WaitCallbackConfigError(
            f"wait_callback.ttl_seconds must be a positive integer, got "
            f"{ttl_raw!r}"
        )
    if ttl_raw < MIN_TTL_SECONDS or ttl_raw > MAX_TTL_SECONDS:
        raise WaitCallbackConfigError(
            f"wait_callback.ttl_seconds must be in [{MIN_TTL_SECONDS}, "
            f"{MAX_TTL_SECONDS}] (24h), got {ttl_raw}. Longer waits "
            "should be split into multiple wait_callbacks or use cron."
        )
    return ttl_raw


def validate_config(wait_callback: Optional[Dict[str, Any]]) -> None:
    """Validate the static author-supplied ``step.wait_callback`` block.

    Raises :class:`WaitCallbackConfigError` for any structural issue.
    Both ``expected_schema`` and ``ttl_seconds`` are optional — the
    minimum valid config is ``{}``.
    """
    if wait_callback is None:
        # Allowed — author wants the defaults
        return
    if not isinstance(wait_callback, dict):
        raise WaitCallbackConfigError(
            "wait_callback step's 'wait_callback' key must be an object "
            f"or null; got {type(wait_callback).__name__}"
        )
    schema = wait_callback.get("expected_schema")
    if schema is not None and not isinstance(schema, dict):
        raise WaitCallbackConfigError(
            "wait_callback.expected_schema must be a JSON Schema object "
            "or null"
        )
    coerce_ttl(wait_callback.get("ttl_seconds"))


# ---------------------------------------------------------------------------
# Token + URL helpers
# ---------------------------------------------------------------------------


def _generate_token() -> str:
    """Cryptographically-strong random token, URL-safe.

    32 bytes of entropy → ~43 url-safe characters. Unguessable by
    brute force in any realistic threat model.
    """
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    """Hex SHA-256 of the plaintext token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def compare_token(received: str, stored_hash: str) -> bool:
    """Constant-time check: does ``received`` hash to ``stored_hash``?

    Wraps the hash + compare so callers never branch on substring
    comparisons that could leak timing.
    """
    if not isinstance(received, str) or not isinstance(stored_hash, str):
        return False
    return hmac.compare_digest(_hash_token(received), stored_hash)


def build_callback_url(execution_id: UUID, token: str) -> str:
    """Compose the full callback URL.

    Uses ``CALLBACK_BASE_URL`` env if set (recommended for production
    so authors get a stable absolute URL). When unset, returns the
    PATH only — the REST endpoint will rewrite it to an absolute URL
    using the request's ``X-Forwarded-Host`` at serve time as a
    last resort. The path is always canonical.
    """
    path = CALLBACK_PATH_TEMPLATE.format(exec_id=execution_id, token=token)
    base = os.getenv("CALLBACK_BASE_URL", "").rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


# ---------------------------------------------------------------------------
# Suspend builder
# ---------------------------------------------------------------------------


def build_suspend(
    step: Dict[str, Any],
    state: ExecutionState,
    execution_id: UUID,
) -> Suspend:
    """Generate token + return the Suspend payload.

    The plaintext token is shipped in ``callback_url`` so the parent
    step (and downstream steps) can read it via ``${current_step.
    callback_url}`` and pass it to the external system. The hash is
    stored alongside for validation; the plaintext token itself is
    NOT stored separately (the URL holds it, but that's the only
    copy in the DB).
    """
    wait_callback = step.get("wait_callback") or {}
    validate_config(wait_callback)
    ttl = coerce_ttl(wait_callback.get("ttl_seconds"))

    token = _generate_token()
    token_hash = _hash_token(token)
    callback_url = build_callback_url(execution_id, token)

    payload: Dict[str, Any] = {
        "step_id": step.get("step_id") or step.get("id"),
        "callback_url": callback_url,
        "token_hash": token_hash,
    }
    expected_schema = wait_callback.get("expected_schema")
    if expected_schema is not None:
        payload["expected_schema"] = expected_schema

    return Suspend(reason="wait_callback", payload=payload, ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# Endpoint-side validation
# ---------------------------------------------------------------------------


def validate_callback(
    suspension_payload: Dict[str, Any],
    received_token: str,
    body: Any,
) -> Tuple[bool, Optional[str]]:
    """Authenticate the token + optionally validate the body schema.

    Returns ``(True, None)`` on success, ``(False, error)`` on
    failure. Errors are intentionally GENERIC for the auth check
    ("invalid token") so we don't leak which part failed.
    """
    stored_hash = (suspension_payload or {}).get("token_hash")
    if not isinstance(stored_hash, str):
        return False, "execution is not waiting on a callback"
    if not compare_token(received_token, stored_hash):
        return False, "invalid token"

    expected_schema = (suspension_payload or {}).get("expected_schema")
    if expected_schema is None:
        return True, None

    # Optional body schema — reuse the elicit helper to keep the
    # validation behaviour consistent.
    from .elicit_step import validate_response as _elicit_validate

    ok, err = _elicit_validate({"schema": expected_schema}, body)
    if not ok:
        return False, err
    return True, None
