"""Smoke tests for the bundled composition starter templates.

The /api/v1/compositions/templates endpoint serves the read-only JSON
file shipped with the registry. Its purpose is to give the empty-state
of the UI a one-click "Use template" entry point per B-1 step type.

We assert:
- 401 without auth (it's auth-gated so we don't disclose templates to
  random scrapers, even though they're public knowledge in the repo).
- 200 + non-empty list with the expected shape for an authed user.
- Each template's composition body has the minimum keys we surface
  in the modal (name, steps with step_id + type) and the step types
  belong to the B-1 vocabulary.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


B1_STEP_TYPES = {
    "elicit",
    "wait_until",
    "wait_callback",
    "approval",
    "subcomposition",
    "tool",
}


async def test_templates_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/compositions/templates")
    assert resp.status_code in (401, 403)


async def test_templates_endpoint_returns_bundled_set(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get(
        "/api/v1/compositions/templates", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body.get("version") == 1
    templates = body.get("templates") or []
    assert len(templates) >= 3, "should ship at least 3 starter templates"

    seen_ids = set()
    for tpl in templates:
        assert tpl["id"] not in seen_ids, f"duplicate id {tpl['id']}"
        seen_ids.add(tpl["id"])

        for required in ("id", "title", "description", "composition"):
            assert required in tpl, f"missing {required} on {tpl.get('id')}"

        comp = tpl["composition"]
        assert "name" in comp and isinstance(comp["name"], str)
        assert "steps" in comp and isinstance(comp["steps"], list) and comp["steps"]

        for step in comp["steps"]:
            assert step.get("step_id"), f"step missing step_id in {tpl['id']}"
            assert step.get("type") in B1_STEP_TYPES, (
                f"unknown step type {step.get('type')!r} in {tpl['id']}"
            )
