"""Security regression test for /api/v1/tool-groups/propose.

The endpoint feeds the org catalogue to the LLM, then trusts the JSON
returned to enumerate `tool_ids`. The handler MUST filter that list
through the candidate set (org-scoped) so a hallucinated UUID — or a
prompt-injected one — that belongs to another org cannot leak into the
proposed toolbox.

This test mocks the LLM HTTP client, injects a foreign UUID alongside
legitimate org-owned IDs, and asserts the foreign one is dropped while
the legitimate ones survive.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.mark.asyncio
async def test_propose_filters_foreign_tool_ids(monkeypatch):
    """A LLM that returns one legitimate org tool + one foreign UUID
    should produce a response with only the legitimate tool."""

    from app.api.v1 import tool_groups as tg_mod
    from app.routers.mcp_gateway.pool.pool_loader import PoolEntry

    org_id = uuid.uuid4()
    legitimate_tool_id = str(uuid.uuid4())
    foreign_tool_id = str(uuid.uuid4())  # not in candidate set

    legitimate_entry = PoolEntry(
        kind="tool",
        id=legitimate_tool_id,
        name="Hostinger__DNS_getDNSRecordsV1",
        description="Read DNS records",
        parameters_schema={"type": "object"},
        server_name="Hostinger",
        server_id=str(uuid.uuid4()),
    )

    async def fake_load_searchable_pool(_db, _org_id):
        return [legitimate_entry]

    # The endpoint imports load_searchable_pool inside the function body,
    # so we patch the source module rather than the importing one.
    from app.routers.mcp_gateway.pool import pool_loader as _pl

    monkeypatch.setattr(_pl, "load_searchable_pool", fake_load_searchable_pool, raising=False)

    # Patch the analyzer's HTTP client to return a JSON proposal that
    # tries to smuggle a foreign UUID alongside the legitimate one.
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(return_value=None)
    fake_response.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "name": "Test toolbox",
                                "description": "Persona for DNS work",
                                "color": "blue",
                                "tool_ids": [legitimate_tool_id, foreign_tool_id],
                                "rationales": {
                                    legitimate_tool_id: "matches",
                                    foreign_tool_id: "evil",
                                },
                                "composition_suggestion": None,
                            }
                        )
                    }
                }
            ]
        }
    )

    fake_http = MagicMock()
    fake_http.post = AsyncMock(return_value=fake_response)

    fake_analyzer = MagicMock()
    fake_analyzer.llm_url = "https://api.mistral.ai/v1"
    fake_analyzer.llm_model = "mistral-small-latest"
    fake_analyzer.http_client = fake_http

    fake_gateway = MagicMock()
    fake_gateway.orchestration_tools.intent_analyzer = fake_analyzer

    # Patch `gateway` resolution inside the endpoint via the import path
    # the endpoint uses (`from ...routers.mcp_unified import gateway`).
    import app.routers.mcp_unified as mcp_unified

    monkeypatch.setattr(mcp_unified, "gateway", fake_gateway, raising=False)

    # Build minimal user / org_context shims, plus a no-op DB stub.
    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    org_context = (MagicMock(), org_id)

    class FakeDB:
        async def execute(self, *_args, **_kwargs):
            class _R:
                def all(self_inner):
                    return []

                def scalars(self_inner):
                    return self_inner

            return _R()

        async def commit(self):
            return None

    payload = tg_mod.ToolGroupProposeRequest(intent="dns operations on hostinger", candidate_limit=40)
    resp = await tg_mod.propose_toolbox(
        payload=payload, user=fake_user, org_context=org_context, db=FakeDB()
    )

    returned_ids = [t.tool_id for t in resp.tools]

    assert legitimate_tool_id in returned_ids, (
        "Legitimate org tool must survive the cross-org filter"
    )
    assert foreign_tool_id not in returned_ids, (
        "Foreign tool ID must be stripped — cross-org leak via LLM hallucination"
    )
    assert resp.candidate_count == 1


@pytest.mark.asyncio
async def test_propose_drops_all_when_llm_returns_only_foreign_ids(monkeypatch):
    """If every ID returned by the LLM is foreign, the response carries
    zero tools and the empty-result note is surfaced."""

    from app.api.v1 import tool_groups as tg_mod
    from app.routers.mcp_gateway.pool.pool_loader import PoolEntry

    org_id = uuid.uuid4()
    legitimate_entry = PoolEntry(
        kind="tool",
        id=str(uuid.uuid4()),
        name="local",
        description="",
        parameters_schema={"type": "object"},
        server_name="X",
        server_id=str(uuid.uuid4()),
    )

    async def fake_load_searchable_pool(_db, _org_id):
        return [legitimate_entry]

    from app.routers.mcp_gateway.pool import pool_loader as _pl

    monkeypatch.setattr(_pl, "load_searchable_pool", fake_load_searchable_pool, raising=False)

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(return_value=None)
    fake_response.json = MagicMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "name": "Cross-org leak",
                                "description": "...",
                                "tool_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
                            }
                        )
                    }
                }
            ]
        }
    )
    fake_http = MagicMock()
    fake_http.post = AsyncMock(return_value=fake_response)

    fake_analyzer = MagicMock()
    fake_analyzer.llm_url = "https://api.mistral.ai/v1"
    fake_analyzer.llm_model = "x"
    fake_analyzer.http_client = fake_http

    fake_gateway = MagicMock()
    fake_gateway.orchestration_tools.intent_analyzer = fake_analyzer

    import app.routers.mcp_unified as mcp_unified

    monkeypatch.setattr(mcp_unified, "gateway", fake_gateway, raising=False)

    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    org_context = (MagicMock(), org_id)

    class FakeDB:
        async def execute(self, *_args, **_kwargs):
            class _R:
                def all(self_inner):
                    return []
                def scalars(self_inner):
                    return self_inner
            return _R()
        async def commit(self):
            return None

    payload = tg_mod.ToolGroupProposeRequest(intent="anything")
    resp = await tg_mod.propose_toolbox(
        payload=payload, user=fake_user, org_context=org_context, db=FakeDB()
    )
    assert resp.tools == []
    assert resp.note is not None
