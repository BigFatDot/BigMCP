"""
Tests for the configurable rerank gating (Chunk 4).

Coverage:
1. ``RERANK_ENABLED=false`` (default) skips the rerank HTTP call entirely
   — even when ``LLM_API_KEY`` is set — and falls back to vector cosine
   ranking.
2. ``RERANK_ENABLED=true`` uses ``Settings.RERANK_MODEL`` instead of the
   previously-hardcoded ``"rerank-small"``.
3. ``RERANK_API_URL`` overrides the default LLM endpoint so a Mistral
   rerank key can sit alongside an Ollama/OpenAI chat endpoint.

We exercise the gating by driving ``MCPRegistry.search_tools`` with a
minimal in-process registry (no DB, no real MCP servers) and an
``httpx.MockTransport`` that records every outbound rerank request.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.models import ToolInfo
from app.core.registry import MCPRegistry


# ---------------------------------------------------------------------------
# Helpers — build a registry with two dummy tools and a no-op vector store
# that returns the tool IDs in insertion order.
# ---------------------------------------------------------------------------


def _make_registry_with_tools() -> MCPRegistry:
    reg = MCPRegistry()

    tools = [
        ToolInfo(
            id="srv.t1",
            name="t1",
            description="First test tool",
            server_id="srv",
        ),
        ToolInfo(
            id="srv.t2",
            name="t2",
            description="Second test tool",
            server_id="srv",
        ),
    ]
    reg.tools = {t.id: t for t in tools}

    # Replace vector store with a fake that returns tool ids in order so
    # search_tools doesn't try real embeddings.
    reg.vector_store = SimpleNamespace(
        search=lambda query, limit: list(reg.tools.keys()),
    )

    # Short-circuit update_tools so search_tools doesn't try to refresh
    # against DB / servers we don't have in unit-test mode.
    async def _noop():
        return None

    reg.update_tools = _noop  # type: ignore[assignment]
    return reg


# ---------------------------------------------------------------------------
# 1. RERANK_ENABLED=false → no httpx rerank call at all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_disabled_skips_http_call(monkeypatch):
    """
    With RERANK_ENABLED=false, ``search_tools`` must NOT instantiate an
    httpx.AsyncClient targeted at /rerank — even when LLM_API_KEY is set.
    We patch AsyncClient.post so any rerank attempt would surface as a
    failed assertion.
    """
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "RERANK_ENABLED", False, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_API_URL", "http://ollama:11434/v1")

    reg = _make_registry_with_tools()

    # If anything tries to call httpx.AsyncClient.post during the test,
    # raise so it shows up loudly.
    with patch.object(
        httpx.AsyncClient,
        "post",
        new=AsyncMock(side_effect=AssertionError("Rerank was called despite RERANK_ENABLED=false")),
    ):
        results = await reg.search_tools(query="anything", limit=5)

    # Fallback path returns enriched tool dicts, in vector-cosine order.
    assert len(results) == 2
    returned_ids = {r.get("id") for r in results}
    assert returned_ids == {"srv.t1", "srv.t2"}


# ---------------------------------------------------------------------------
# 2. RERANK_ENABLED=true → uses Settings.RERANK_MODEL in body, not hardcoded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_enabled_uses_configured_model(monkeypatch):
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "RERANK_ENABLED", True, raising=False)
    monkeypatch.setattr(core_settings, "RERANK_MODEL", "mybackend-rerank", raising=False)
    monkeypatch.setattr(core_settings, "RERANK_API_URL", None, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_API_URL", "https://api.mistral.ai/v1")

    reg = _make_registry_with_tools()

    captured = {}

    async def _fake_post(self, url, json=None, *args, **kwargs):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 1, "relevance_score": 0.5},
                ]
            },
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.AsyncClient, "post", new=_fake_post):
        results = await reg.search_tools(query="find me a tool", limit=5)

    assert captured, "rerank endpoint was never called"
    assert captured["json"]["model"] == "mybackend-rerank", (
        f"Expected configured RERANK_MODEL in body, got: {captured['json']}"
    )
    assert captured["json"]["prompt"] == "find me a tool"
    # 2 tools in, 2 tools back in rerank-relevance order.
    assert len(results) == 2
    assert results[0].get("id") == "srv.t1"


# ---------------------------------------------------------------------------
# 3. RERANK_API_URL overrides LLM_API_URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_api_url_override(monkeypatch):
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "RERANK_ENABLED", True, raising=False)
    monkeypatch.setattr(core_settings, "RERANK_MODEL", "rerank-small", raising=False)
    monkeypatch.setattr(
        core_settings, "RERANK_API_URL", "http://custom:9000/v1", raising=False
    )
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("LLM_API_URL", "http://ollama:11434/v1")

    reg = _make_registry_with_tools()

    captured = {}

    async def _fake_post(self, url, json=None, *args, **kwargs):  # noqa: A002
        captured["url"] = url
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.9}]},
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.AsyncClient, "post", new=_fake_post):
        await reg.search_tools(query="any", limit=5)

    assert captured.get("url") == "http://custom:9000/v1/rerank", (
        f"Expected custom rerank endpoint, got: {captured.get('url')}"
    )
    # Make sure the Ollama URL did NOT leak into the rerank call.
    assert "ollama" not in captured["url"]


# ---------------------------------------------------------------------------
# 4. RERANK_ENABLED=true but no LLM_API_KEY → still skip (no auth header to send)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rerank_skipped_without_api_key(monkeypatch):
    from app.core.config import settings as core_settings

    monkeypatch.setattr(core_settings, "RERANK_ENABLED", True, raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_URL", "http://ollama:11434/v1")

    reg = _make_registry_with_tools()

    with patch.object(
        httpx.AsyncClient,
        "post",
        new=AsyncMock(side_effect=AssertionError("Rerank was attempted without an API key")),
    ):
        results = await reg.search_tools(query="x", limit=5)

    assert len(results) == 2
