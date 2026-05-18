"""
Unit tests for the `search` MCP tool handler — pure logic only.

Integration tests that touch the DB / notifications live under
tests/integration/ and will be added in Phase 6.1.
"""

import pytest

from app.routers.mcp_gateway.pool import POOL_TOOL_NAMES, get_pool_tools
from app.routers.mcp_gateway.pool.search_handler import (
    _score_tool,
    _tokenize,
    handle_search,
)


class _FakeTool:
    def __init__(self, tool_name, description="", display_name=None, tags=None, category=None):
        self.tool_name = tool_name
        self.description = description
        self.display_name = display_name
        self.tags = tags
        self.category = category


def test_pool_tools_definitions_have_search_execute_and_describe():
    """Phase 1 added ``describe_tool`` so the LLM can fetch the verbose
    description on demand when ``MCP_COMPACT_MODE`` ships only titles.
    Phase B-0 chunk 8 added ``composition_status`` for durable workflow polling."""
    tools = get_pool_tools()
    names = {t["name"] for t in tools}
    assert names == POOL_TOOL_NAMES == {
        "search",
        "execute",
        "describe_tool",
        "composition_status",
    }


def test_search_input_schema_requires_query():
    tools = {t["name"]: t for t in get_pool_tools()}
    assert tools["search"]["inputSchema"]["required"] == ["query"]


def test_execute_input_schema_has_no_required_fields():
    """`execute` accepts goal | tool_name | composition_id; none individually required."""
    tools = {t["name"]: t for t in get_pool_tools()}
    assert tools["execute"]["inputSchema"].get("required", []) == []


def test_tokenize_lowercases_and_splits():
    assert _tokenize("Create-GitHub Issue!") == ["create", "github", "issue"]


def test_score_tool_zero_when_no_overlap():
    tool = _FakeTool("send_email", description="Sends an email")
    assert _score_tool(["dns"], tool, "Mail") == 0


def test_score_tool_higher_for_name_match():
    tool = _FakeTool("create_dns_record", description="Creates a DNS record")
    score_name = _score_tool(["dns"], tool, "Hostinger")
    tool2 = _FakeTool("update_record", description="Updates a DNS record")
    score_desc = _score_tool(["dns"], tool2, "Hostinger")
    # Name match adds +2 (tool_name) + +1 (haystack) vs +1 description-only.
    assert score_name > score_desc


def test_score_tool_aggregates_multi_token():
    tool = _FakeTool(
        "create_dns_record",
        description="Creates a DNS record on Hostinger",
        tags=["dns", "hostinger"],
    )
    score = _score_tool(["create", "dns", "hostinger"], tool, "Hostinger")
    assert score >= 4  # at least one hit per token, with name boosts


@pytest.mark.asyncio
async def test_handle_search_rejects_empty_query():
    result = await handle_search({"query": "  "}, user_id="u", organization_id="o")
    assert "error" in result


@pytest.mark.asyncio
async def test_handle_search_rejects_invalid_mode():
    result = await handle_search(
        {"query": "github", "mode": "wipe"},
        user_id="u",
        organization_id="o",
    )
    assert "error" in result and "mode" in result["error"].lower()


@pytest.mark.asyncio
async def test_handle_search_requires_auth_context():
    result = await handle_search(
        {"query": "github"},
        user_id=None,
        organization_id=None,
    )
    assert "error" in result
    assert "auth" in result["error"].lower()
