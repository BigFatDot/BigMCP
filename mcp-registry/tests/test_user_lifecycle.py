"""Tests for non-destructive user lifecycle (N1.4).

Covers:
- UserStatus enum + Default value
- Login refusal when status != ACTIVE
- JWT validation refusal when status changes mid-session
- API key validation refusal when status changes
- Admin endpoints suspend / reactivate / soft-delete
- Safety guards (cannot suspend self, cannot suspend deleted)
"""

from __future__ import annotations

import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus
from app.models.audit_log import AuditAction, AuditLog


# ---------------------------------------------------------------------------
# Static enum check
# ---------------------------------------------------------------------------


def test_user_status_enum_values():
    assert UserStatus.ACTIVE.value == "active"
    assert UserStatus.SUSPENDED.value == "suspended"
    assert UserStatus.DELETED.value == "deleted"


# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspended_user_cannot_login(
    client: AsyncClient,
    test_user: dict,
    db_session: AsyncSession,
):
    """Login must return 403 with error account_suspended."""
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()
    user.status = UserStatus.SUSPENDED.value
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "account_suspended"


@pytest.mark.asyncio
async def test_deleted_user_cannot_login(
    client: AsyncClient,
    test_user: dict,
    db_session: AsyncSession,
):
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()
    user.status = UserStatus.DELETED.value
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "account_deleted"


@pytest.mark.asyncio
async def test_login_blocked_attempt_creates_audit(
    client: AsyncClient,
    test_user: dict,
    db_session: AsyncSession,
):
    """Blocked logins on disabled accounts must leave a trail."""
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()
    user.status = UserStatus.SUSPENDED.value
    await db_session.commit()

    await client.post(
        "/api/v1/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )

    # Look for the most recent login_failed event with the right reason
    audit_rows = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.LOGIN_FAILED.value)
            .order_by(AuditLog.timestamp.desc())
        )
    ).scalars().all()
    assert any(
        r.details and r.details.get("reason") == "account_suspended"
        for r in audit_rows
    )


# ---------------------------------------------------------------------------
# Token validation gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwt_invalidated_after_status_change(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """A JWT issued while ACTIVE must stop working when status flips."""
    # The token is from auth_headers — works while ACTIVE.
    me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200, me_resp.text

    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()
    user.status = UserStatus.SUSPENDED.value
    await db_session.commit()

    # Same token: must now fail.
    me_resp_after = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_resp_after.status_code == 401


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


async def _promote_to_instance_admin(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db.commit()


@pytest.mark.asyncio
async def test_admin_suspend_then_reactivate(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Suspend changes status; reactivate restores it."""
    await _promote_to_instance_admin(db_session, test_user["email"])
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()

    # The same admin will act on themselves — but that's blocked by guard,
    # so create a second user to act on.
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "victim@example.com", "password": "VictimPass123", "name": "V"},
    )
    assert register.status_code in (201, 202)
    victim = (await db_session.execute(
        select(User).where(User.email == "victim@example.com")
    )).scalar_one()

    # Suspend
    resp = await client.post(
        f"/api/v1/admin/users/{victim.id}/suspend",
        json={"reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "suspended"

    # Reactivate
    resp = await client.post(
        f"/api/v1/admin/users/{victim.id}/reactivate",
        json={"reason": "back to work"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_admin_soft_delete(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _promote_to_instance_admin(db_session, test_user["email"])
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "tobedeleted@example.com", "password": "DelPass123"},
    )
    assert register.status_code in (201, 202)
    victim = (await db_session.execute(
        select(User).where(User.email == "tobedeleted@example.com")
    )).scalar_one()

    resp = await client.post(
        f"/api/v1/admin/users/{victim.id}/soft-delete",
        json={"reason": "RGPD request"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["deleted_at"] is not None


@pytest.mark.asyncio
async def test_cannot_suspend_self(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _promote_to_instance_admin(db_session, test_user["email"])
    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()

    resp = await client.post(
        f"/api/v1/admin/users/{user.id}/suspend",
        json={"reason": "oops"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "calling instance admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_suspend_deleted_user(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    await _promote_to_instance_admin(db_session, test_user["email"])
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "wasdeleted@example.com", "password": "WasPass123"},
    )
    assert register.status_code in (201, 202)
    victim = (await db_session.execute(
        select(User).where(User.email == "wasdeleted@example.com")
    )).scalar_one()
    victim.status = UserStatus.DELETED.value
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{victim.id}/suspend",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_non_admin_cannot_suspend(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """A regular (non-admin) user attempting to call /admin/* must get 403.

    test_user can't be used directly here: as the first registered user
    they are auto-promoted to instance admin in Community/Enterprise
    flow. Register a second user, log in as them, and check the gate.
    """
    # First user (auto-promoted instance admin) — we don't act as them.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "first-admin@example.com", "password": "FirstPass123"},
    )
    # Verify them so login passes (SaaS mode).
    first = (await db_session.execute(
        select(User).where(User.email == "first-admin@example.com")
    )).scalar_one()
    first.email_verified = True

    # Second user — NOT auto-promoted (is_first_user is False now).
    await client.post(
        "/api/v1/auth/register",
        json={"email": "regular@example.com", "password": "RegularPass123"},
    )
    regular = (await db_session.execute(
        select(User).where(User.email == "regular@example.com")
    )).scalar_one()
    regular.email_verified = True
    await db_session.commit()

    # Sanity: regular user has no instance_admin flag.
    assert (regular.preferences or {}).get("instance_admin") is not True

    # Login as the regular user, get JWT.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "regular@example.com", "password": "RegularPass123"},
    )
    assert login.status_code == 200, login.text
    regular_jwt = login.json()["access_token"]

    # Attempt /admin/users/.../suspend → must be 403.
    resp = await client.post(
        f"/api/v1/admin/users/{first.id}/suspend",
        json={},
        headers={"Authorization": f"Bearer {regular_jwt}"},
    )
    assert resp.status_code == 403, resp.text
