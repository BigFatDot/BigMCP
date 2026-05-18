"""Community edition single-user enforcement.

Validates that ``/api/v1/auth/register`` honors the edition-level seat
cap returned by ``app.core.edition.get_max_users``. Community returns
``1``; Enterprise / Cloud SaaS return ``999999`` (effectively unlimited).

We monkeypatch ``get_max_users`` directly so the test is independent
of the runtime ``EDITION`` env var.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_second_signup_rejected_when_seat_cap_is_one(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """With max_users=1, the second signup is blocked with 403."""
    # Pretend we're on Community edition: 1-user cap.
    monkeypatch.setattr(
        "app.core.edition.get_max_users", lambda: 1
    )

    first = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "solo-operator@example.com",
            "password": "FirstUser123!",
            "name": "Solo",
        },
    )
    assert first.status_code in (201, 202), first.text

    second = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "would-be-team-mate@example.com",
            "password": "SecondUser123!",
            "name": "Second",
        },
    )
    assert second.status_code == 403, second.text
    detail = second.json()["detail"].lower()
    assert "user limit" in detail
    assert "community" in detail


async def test_signup_uncapped_when_max_users_is_large(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Sanity: with a large cap (Enterprise/SaaS), signups are not gated."""
    monkeypatch.setattr(
        "app.core.edition.get_max_users", lambda: 999999
    )

    for i in range(2):
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"uncapped-user-{i}@example.com",
                "password": "UncappedPass123!",
                "name": f"User {i}",
            },
        )
        assert resp.status_code in (201, 202), resp.text
