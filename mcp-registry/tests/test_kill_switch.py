"""Tests for the cross-surface kill-switch (N1.3).

POST /admin/users/{id}/revoke-all must invalidate JWT, refresh tokens,
and API keys atomically. Each surface is verified independently here:

- JWT issued before revocation → 401 at next /auth/me
- API key issued before revocation → 401 (validate_api_key returns None)
- /auth/refresh with the old refresh token → 401
- self-revoke is forbidden
"""

from __future__ import annotations

import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.user import User


async def _promote_to_instance_admin(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db.commit()


@pytest.mark.asyncio
async def test_apikey_revoke_helper():
    """APIKey.revoke() mirrors RefreshToken.revoke()."""
    key = APIKey(
        scopes=["tools:read"],
        is_active=True,
    )
    assert key.revoked_at is None
    key.revoke(reason="test")
    assert key.is_active is False
    assert key.revoked_at is not None
    assert key.revoked_reason == "test"


@pytest.mark.asyncio
async def test_revoke_all_kills_jwt(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """JWT issued before revoke-all stops working immediately after."""
    await _promote_to_instance_admin(db_session, test_user["email"])

    # Confirm JWT works.
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text

    user = (await db_session.execute(
        select(User).where(User.email == test_user["email"])
    )).scalar_one()

    # Self-revoke is blocked — register a victim to act on.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "victim-killswitch@example.com", "password": "VicPass123"},
    )
    victim = (await db_session.execute(
        select(User).where(User.email == "victim-killswitch@example.com")
    )).scalar_one()
    victim.email_verified = True
    await db_session.commit()

    # Login as the victim, get JWT.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "victim-killswitch@example.com", "password": "VicPass123"},
    )
    assert login.status_code == 200, login.text
    victim_jwt = login.json()["access_token"]
    victim_refresh = login.json()["refresh_token"]
    victim_headers = {"Authorization": f"Bearer {victim_jwt}"}

    # Sanity: victim JWT works.
    sanity = await client.get("/api/v1/auth/me", headers=victim_headers)
    assert sanity.status_code == 200

    # Make sure the revoke-all timestamp lands STRICTLY after the
    # token's iat (resolution: 1 second). datetime.utcfromtimestamp(iat)
    # truncates to seconds, so we need an extra second of separation.
    await asyncio.sleep(1.5)

    # Revoke-all on the victim.
    resp = await client.post(
        f"/api/v1/admin/users/{victim.id}/revoke-all",
        json={"reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_keys_revoked"] >= 0
    assert body["refresh_tokens_revoked"] >= 0

    # Victim JWT must now be 401.
    after = await client.get("/api/v1/auth/me", headers=victim_headers)
    assert after.status_code == 401

    # Refresh token also must be rejected.
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": victim_refresh},
    )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_revoke_all_kills_api_key(
    client: AsyncClient,
    test_user: dict,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """API key issued before revoke-all becomes invalid afterwards."""
    await _promote_to_instance_admin(db_session, test_user["email"])

    # Register + login a victim.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "ak-victim@example.com", "password": "AKPass123"},
    )
    victim = (await db_session.execute(
        select(User).where(User.email == "ak-victim@example.com")
    )).scalar_one()
    victim.email_verified = True
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ak-victim@example.com", "password": "AKPass123"},
    )
    assert login.status_code == 200
    victim_jwt = login.json()["access_token"]
    victim_headers = {"Authorization": f"Bearer {victim_jwt}"}

    # Victim creates an API key with credentials:read scope.
    create = await client.post(
        "/api/v1/api-keys",
        json={"name": "victim-key", "scopes": ["credentials:read"]},
        headers=victim_headers,
    )
    assert create.status_code == 201, create.text
    api_secret = create.json()["secret"]

    # Sanity: API key works on /auth/me (dual-auth endpoint).
    sanity = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_secret}"},
    )
    assert sanity.status_code == 200

    # Force time gap.
    await asyncio.sleep(1.5)

    # Revoke-all on the victim.
    revoke = await client.post(
        f"/api/v1/admin/users/{victim.id}/revoke-all",
        json={},
        headers=auth_headers,
    )
    assert revoke.status_code == 200, revoke.text
    assert revoke.json()["api_keys_revoked"] >= 1

    # Now the API key must be rejected.
    after = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {api_secret}"},
    )
    assert after.status_code == 401


@pytest.mark.asyncio
async def test_cannot_revoke_self(
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
        f"/api/v1/admin/users/{user.id}/revoke-all",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 400
