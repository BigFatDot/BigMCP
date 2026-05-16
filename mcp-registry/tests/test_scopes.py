"""
Tests for API key scope enforcement (`require_scope` dependency).

Validates the log_only / enforce modes introduced as part of N0 hardening
of the access-control roadmap. See ROADMAP_ACCESS_CONTROL.md.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey, APIKeyScope
from app.models.audit_log import AuditLog, AuditAction


# ---------------------------------------------------------------------------
# Enum check — APIKEY_SCOPE_DENIED must exist (N0 prerequisite)
# ---------------------------------------------------------------------------


def test_apikey_scope_denied_action_exists():
    """The AuditAction enum must define APIKEY_SCOPE_DENIED."""
    assert hasattr(AuditAction, "APIKEY_SCOPE_DENIED")
    assert AuditAction.APIKEY_SCOPE_DENIED.value == "security.apikey_scope_denied"


# ---------------------------------------------------------------------------
# APIKey.has_scope sanity (admin scope grants everything)
# ---------------------------------------------------------------------------


def test_api_key_has_scope_admin_override():
    """A key with the `admin` scope must satisfy any scope check."""
    key = APIKey(
        scopes=[APIKeyScope.ADMIN.value],
    )
    assert key.has_scope("tools:read")
    assert key.has_scope("credentials:write")
    assert key.has_scope("servers:write")


def test_api_key_has_scope_exact_match():
    """A key matches only its declared scopes (no implicit broadening)."""
    key = APIKey(
        scopes=["tools:read"],
    )
    assert key.has_scope("tools:read")
    assert not key.has_scope("tools:execute")
    assert not key.has_scope("credentials:read")


# ---------------------------------------------------------------------------
# Integration — require_scope(log_only=True) allows under-scoped requests
# but records the denial in the audit log.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_only_lets_under_scoped_api_key_through(
    client: AsyncClient,
    test_api_key: dict,
    db_session: AsyncSession,
):
    """
    A request authenticated with an API key that lacks `credentials:read`
    must still succeed under log_only mode (no 403), but an audit entry
    of type APIKEY_SCOPE_DENIED must have been written.
    """
    # test_api_key fixture grants only tools:read + tools:execute.
    # GET /user-credentials/ requires credentials:read (log_only).
    response = await client.get(
        "/api/v1/user-credentials/",
        headers={"Authorization": f"Bearer {test_api_key['secret']}"},
    )

    # log_only mode: request must NOT be blocked by missing scope.
    # Other auth failures (401) are also acceptable here since the
    # fixture's organization context may differ, but we never expect 403
    # to come from require_scope.
    assert response.status_code != 403, (
        f"require_scope in log_only mode must not block; got 403 with "
        f"detail={response.text}"
    )

    # An audit entry must have been written.
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.APIKEY_SCOPE_DENIED.value
        )
    )
    entries = result.scalars().all()

    assert len(entries) >= 1, "Expected at least one APIKEY_SCOPE_DENIED audit log"
    entry = entries[0]
    assert entry.resource_type == "api_key"
    assert entry.details is not None
    assert entry.details.get("scope_required") == "credentials:read"
    assert entry.details.get("enforce_mode") == "log_only"


# ---------------------------------------------------------------------------
# Unit — require_scope(log_only=False) raises 403 when scope is missing.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_mode_raises_403_when_scope_missing(
    db_session: AsyncSession,
):
    """
    Direct invocation of the inner check_scope coroutine with log_only=False
    and an API key that lacks the requested scope must raise HTTPException 403.
    """
    from fastapi import HTTPException

    from app.api.dependencies import require_scope
    from app.models.user import User

    dep = require_scope("credentials:write", log_only=False)

    # Build a minimal in-memory API key (no DB persistence required for this
    # path — we only exercise the scope check + raise).
    user = User(email="scopes@example.com")
    api_key = APIKey(
        name="under-scoped",
        scopes=["tools:read"],
        key_prefix="mcphub_sk_xxxxxxx",
    )

    with pytest.raises(HTTPException) as exc_info:
        # check_scope is the coroutine returned by the factory; call it directly.
        await dep(request=None, auth=(user, api_key), db=db_session)

    assert exc_info.value.status_code == 403
    assert "credentials:write" in exc_info.value.detail


@pytest.mark.asyncio
async def test_enforce_mode_passes_when_scope_present(
    db_session: AsyncSession,
):
    """When the key declares the required scope, the dependency must return None."""
    from app.api.dependencies import require_scope
    from app.models.user import User

    dep = require_scope("credentials:read", log_only=False)

    user = User(email="scopes-ok@example.com")
    api_key = APIKey(
        name="scoped",
        scopes=["credentials:read"],
        key_prefix="mcphub_sk_yyyyyyy",
    )

    result = await dep(request=None, auth=(user, api_key), db=db_session)
    assert result is None


@pytest.mark.asyncio
async def test_jwt_auth_bypasses_scope_check(
    db_session: AsyncSession,
):
    """JWT-authenticated users currently have all scopes (no api_key in auth)."""
    from app.api.dependencies import require_scope
    from app.models.user import User

    dep = require_scope("credentials:write", log_only=False)

    user = User(email="jwt@example.com")

    # auth tuple with no api_key -> JWT path -> all scopes granted.
    result = await dep(request=None, auth=(user, None), db=db_session)
    assert result is None


# ---------------------------------------------------------------------------
# SCOPE_ENFORCE_MODE env-driven feature flag (B-1 post-audit consolidation).
# Operators flip enforcement on/off globally without redeploying code.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_env_enforce_overrides_callsite_log_only(
    db_session: AsyncSession, monkeypatch
):
    """SCOPE_ENFORCE_MODE=enforce forces deny even if the call site
    declared log_only=True (the master switch for rolling enforcement
    on without touching the 33 existing call sites)."""
    from fastapi import HTTPException
    from app.api.dependencies import require_scope
    from app.models.user import User

    monkeypatch.setenv("SCOPE_ENFORCE_MODE", "enforce")
    dep = require_scope("credentials:write", log_only=True)  # would have allowed before
    user = User(email="override-enforce@example.com")
    api_key = APIKey(
        name="under-scoped",
        scopes=["tools:read"],
        key_prefix="mcphub_sk_envtest1",
    )
    with pytest.raises(HTTPException) as exc_info:
        await dep(request=None, auth=(user, api_key), db=db_session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_env_log_only_overrides_callsite_enforce(
    db_session: AsyncSession, monkeypatch
):
    """SCOPE_ENFORCE_MODE=log_only is the emergency rollback knob:
    forces audit-only even if the call site declared log_only=False."""
    from app.api.dependencies import require_scope
    from app.models.user import User

    monkeypatch.setenv("SCOPE_ENFORCE_MODE", "log_only")
    dep = require_scope("credentials:write", log_only=False)
    user = User(email="override-logonly@example.com")
    api_key = APIKey(
        name="under-scoped",
        scopes=["tools:read"],
        key_prefix="mcphub_sk_envtest2",
    )
    result = await dep(request=None, auth=(user, api_key), db=db_session)
    assert result is None  # let through despite missing scope


@pytest.mark.asyncio
async def test_env_unset_falls_back_to_callsite_default(
    db_session: AsyncSession, monkeypatch
):
    """Default behaviour: when SCOPE_ENFORCE_MODE is unset, the call
    site's own log_only= argument wins. Existing 33 call sites pass
    log_only=True, so today's behaviour stays identical until an op
    actively sets the env."""
    from app.api.dependencies import require_scope
    from app.models.user import User

    monkeypatch.delenv("SCOPE_ENFORCE_MODE", raising=False)
    dep = require_scope("credentials:write", log_only=True)
    user = User(email="env-unset@example.com")
    api_key = APIKey(
        name="under-scoped",
        scopes=["tools:read"],
        key_prefix="mcphub_sk_envtest3",
    )
    result = await dep(request=None, auth=(user, api_key), db=db_session)
    assert result is None


@pytest.mark.asyncio
async def test_env_garbage_value_falls_back_to_callsite_default(
    db_session: AsyncSession, monkeypatch
):
    """Unknown SCOPE_ENFORCE_MODE values (typo, deprecated alias) MUST
    NOT silently change behaviour — fall back to the call site's
    explicit decision. Prevents an operator typo from accidentally
    flipping the enforcement mode."""
    from app.api.dependencies import require_scope
    from app.models.user import User

    monkeypatch.setenv("SCOPE_ENFORCE_MODE", "shadow")  # not a valid mode
    dep = require_scope("credentials:write", log_only=True)
    user = User(email="env-garbage@example.com")
    api_key = APIKey(
        name="under-scoped",
        scopes=["tools:read"],
        key_prefix="mcphub_sk_envtest4",
    )
    result = await dep(request=None, auth=(user, api_key), db=db_session)
    assert result is None  # callsite log_only=True wins
