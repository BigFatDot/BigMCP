"""
Tests for the LemonSqueezy webhook anti-replay idempotency layer.

The endpoint validates HMAC SHA256, then fingerprints the raw body with
sha256 and inserts a row into ``lemonsqueezy_webhook_events`` BEFORE
running the handler. A duplicate fingerprint returns 200 already_processed
without re-invoking the handler.

These tests bypass the actual subscription/order handlers (which would
need a fully wired LemonSqueezy fixture) by monkeypatching the
EVENT_HANDLERS mapping to a counting stub. That isolates the idempotency
machinery from billing semantics.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import webhooks as webhooks_module
from app.core.config import settings
from app.models.lemonsqueezy_webhook_event import LemonSqueezyWebhookEvent


# Webhook router is only mounted on CLOUD_SAAS. On other editions the
# endpoint 404s, which makes these tests vacuous — skip cleanly.
def _webhook_mounted(client: AsyncClient) -> bool:
    """Return True iff /api/v1/webhooks/lemonsqueezy is routable."""
    from app.main import app  # local import to avoid load-order surprises

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.endswith("/webhooks/lemonsqueezy"):
            return True
    return False


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _payload(event_name: str = "subscription_created", sub_id: str = "sub_1") -> Dict[str, Any]:
    return {
        "meta": {
            "event_name": event_name,
            "custom_data": {"organization_id": "00000000-0000-0000-0000-000000000000"},
        },
        "data": {
            "id": sub_id,
            "attributes": {
                "customer_id": "cus_1",
                "variant_id": "variant_individual",
                "status": "active",
                "created_at": "2026-05-31T22:00:00Z",
                "renews_at": "2026-06-30T22:00:00Z",
                "cancelled": False,
            },
        },
    }


@pytest.fixture(autouse=True)
def _stub_handler(monkeypatch):
    """Replace EVENT_HANDLERS with a counting stub so we measure invocations.

    The stub mutates a list bound on the module so the test can read it
    back after the request returns. We restore the original mapping at
    teardown via monkeypatch.
    """
    calls: list[str] = []

    async def stub(event_data, db):
        calls.append(event_data.get("meta", {}).get("event_name", "?"))

    monkeypatch.setattr(
        webhooks_module,
        "EVENT_HANDLERS",
        {
            "subscription_created": stub,
            "subscription_updated": stub,
            "subscription_cancelled": stub,
        },
    )
    return calls


@pytest.fixture(autouse=True)
def _configure_webhook_secret(monkeypatch):
    """Ensure HMAC verification path is exercised with a known secret."""
    monkeypatch.setattr(
        settings,
        "lemonsqueezy_webhook_secret",
        "test_secret_for_idempotency_tests",
    )


@pytest.mark.asyncio
async def test_webhook_replay_returns_already_processed(
    client: AsyncClient,
    db_session: AsyncSession,
    _stub_handler: list[str],
):
    """Same payload sent twice: handler runs once, second call short-circuits."""
    if not _webhook_mounted(client):
        pytest.skip("Webhook router not mounted on this edition")

    body = json.dumps(_payload()).encode("utf-8")
    signature = _sign(body, settings.lemonsqueezy_webhook_secret)
    headers = {"X-Signature": signature, "Content-Type": "application/json"}

    # First delivery — should process the event cleanly.
    r1 = await client.post(
        "/api/v1/webhooks/lemonsqueezy", content=body, headers=headers
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["status"] == "success"
    assert body1["event"] == "subscription_created"
    event_id = body1["event_id"]
    assert len(event_id) == 64  # sha256 hex

    # Idempotency row should exist with processed_at populated.
    row_q = await db_session.execute(
        select(LemonSqueezyWebhookEvent).where(
            LemonSqueezyWebhookEvent.event_id == event_id
        )
    )
    row = row_q.scalar_one()
    assert row.processed_at is not None
    assert row.error is None
    assert row.event_name == "subscription_created"
    assert row.payload_hash == event_id

    # Second delivery — identical bytes → replay.
    r2 = await client.post(
        "/api/v1/webhooks/lemonsqueezy", content=body, headers=headers
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["status"] == "already_processed"
    assert body2["event_id"] == event_id

    # Handler called exactly once across the two deliveries.
    assert _stub_handler == ["subscription_created"], (
        f"Expected handler to be called exactly once, got {_stub_handler}"
    )

    # Still exactly one idempotency row.
    all_rows = await db_session.execute(select(LemonSqueezyWebhookEvent))
    assert len(list(all_rows.scalars().all())) == 1


@pytest.mark.asyncio
async def test_webhook_distinct_payloads_processed_independently(
    client: AsyncClient,
    db_session: AsyncSession,
    _stub_handler: list[str],
):
    """Two distinct payloads (different sub_id) → two handler invocations."""
    if not _webhook_mounted(client):
        pytest.skip("Webhook router not mounted on this edition")

    secret = settings.lemonsqueezy_webhook_secret

    body_a = json.dumps(_payload(sub_id="sub_A")).encode("utf-8")
    body_b = json.dumps(_payload(sub_id="sub_B")).encode("utf-8")

    sig_a = _sign(body_a, secret)
    sig_b = _sign(body_b, secret)

    r_a = await client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=body_a,
        headers={"X-Signature": sig_a, "Content-Type": "application/json"},
    )
    assert r_a.status_code == 200, r_a.text
    assert r_a.json()["status"] == "success"

    r_b = await client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=body_b,
        headers={"X-Signature": sig_b, "Content-Type": "application/json"},
    )
    assert r_b.status_code == 200, r_b.text
    assert r_b.json()["status"] == "success"

    # Distinct event_ids (different fingerprints).
    assert r_a.json()["event_id"] != r_b.json()["event_id"]

    # Handler called twice.
    assert _stub_handler == ["subscription_created", "subscription_created"]

    # Two idempotency rows persisted.
    rows = (await db_session.execute(select(LemonSqueezyWebhookEvent))).scalars().all()
    assert len(rows) == 2
    assert {r.processed_at is not None for r in rows} == {True}
