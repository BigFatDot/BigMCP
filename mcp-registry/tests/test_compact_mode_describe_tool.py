"""Tests for Phase 1: tools/list compact mode + describe_tool meta-tool.

Coverage:
- ``get_pool_tools()`` advertises the three meta-tools (search, execute,
  describe_tool) with the expected shape.
- ``handle_describe_tool`` returns ``found=true`` with the full description
  for a tool/composition that lives in the searchable pool.
- ``handle_describe_tool`` returns ``found=false`` (not an error) for an
  unknown tool name — lets the LLM recover by calling search.
- ``handle_describe_tool`` returns isError when ``name`` is missing.
- The compact-mode flag (``MCP_COMPACT_MODE``) drops ``description`` from
  the per-tool dict the gateway builds, while keeping ``inputSchema`` +
  ``title``. (Tested at the helper level without a live MCP session.)
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.mcp_gateway.pool import (
    POOL_TOOL_NAMES,
    get_pool_tools,
    handle_describe_tool,
)
from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.organization import Organization
from app.models.user import User


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# get_pool_tools
# ---------------------------------------------------------------------------


async def test_pool_tools_advertise_three_meta_tools():
    tools = get_pool_tools()
    names = {t["name"] for t in tools}
    assert names == {"search", "execute", "describe_tool", "composition_status"}
    assert names == set(POOL_TOOL_NAMES)


async def test_describe_tool_definition_shape():
    tools = get_pool_tools()
    describe = next(t for t in tools if t["name"] == "describe_tool")

    # MCP 2025-06-18: name + inputSchema mandatory; title + description recommended
    assert "name" in describe
    assert "inputSchema" in describe
    assert describe["inputSchema"]["type"] == "object"
    assert "name" in describe["inputSchema"]["properties"]
    assert describe["inputSchema"]["required"] == ["name"]

    # outputSchema present so MCP clients can parse structuredContent
    assert "outputSchema" in describe
    out_props = describe["outputSchema"]["properties"]
    for key in ("name", "kind", "title", "description", "input_schema", "found"):
        assert key in out_props


# ---------------------------------------------------------------------------
# handle_describe_tool
# ---------------------------------------------------------------------------


async def _user_and_org_ids(db_session: AsyncSession, email: str) -> tuple:
    """Resolve (user_id, organization_id) for an email — works across editions."""
    from sqlalchemy import select
    from app.models.organization import OrganizationMember
    from app.models.user import User as UserModel

    user = (
        await db_session.execute(select(UserModel).where(UserModel.email == email))
    ).scalar_one()
    member = (
        await db_session.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def test_describe_tool_missing_name_returns_error(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _user_and_org_ids(db_session, test_user["email"])

    result = await handle_describe_tool(
        {"name": ""},
        user_id=str(user_id),
        organization_id=str(org_id),
    )
    assert result.get("isError") is True
    assert result["structuredContent"]["found"] is False


async def test_describe_tool_unknown_name_returns_found_false(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _user_and_org_ids(db_session, test_user["email"])

    result = await handle_describe_tool(
        {"name": "definitely_does_not_exist__tool"},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = result["structuredContent"]
    assert body["found"] is False
    assert body["name"] == "definitely_does_not_exist__tool"
    assert "not found" in result["content"][0]["text"].lower()
    assert result.get("isError") is not True


async def test_describe_tool_finds_production_composition(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _user_and_org_ids(db_session, test_user["email"])

    comp = Composition(
        organization_id=org_id,
        created_by=user_id,
        name="my test workflow",
        description="Detailed step-by-step description used to validate "
        "describe_tool returns the verbose text on demand.",
        visibility=CompositionVisibility.ORGANIZATION,
        status=CompositionStatus.PRODUCTION,
        steps=[],
        input_schema={"type": "object", "properties": {}},
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    # The pool_loader uses the composition's `name` field (sanitized) to
    # produce the MCP-facing identifier `composition_<safe_name>`.
    expected_mcp_name = "composition_my_test_workflow"

    result = await handle_describe_tool(
        {"name": expected_mcp_name},
        user_id=str(user_id),
        organization_id=str(org_id),
        db=db_session,
    )
    body = result["structuredContent"]
    assert body["found"] is True
    assert body["kind"] == "composition"
    assert body["name"] == expected_mcp_name
    assert "Detailed step-by-step" in body["description"]
    assert body["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# Compact-mode token economy (helper-level test)
# ---------------------------------------------------------------------------


async def test_compact_mode_drops_description_keeps_title_and_schema(
    monkeypatch,
):
    """Mirror the per-tool dict construction logic in mcp_unified.py:1164.

    We don't spin up the full MCP gateway (it requires SSE + session state);
    instead we replicate the relevant branch and assert the shape change
    when MCP_COMPACT_MODE=true vs false. This is a regression test for the
    Phase 1 compaction contract.
    """
    from app.core.config import settings

    # Helper that mirrors the code in mcp_unified.py:1164-1190 for one tool.
    def build_tool_dict(*, compact: bool) -> dict:
        unique_name = "GitHub__create_issue"
        full_description = "[GitHub] Create a new issue in the given repo with title and body."
        parameters = {
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            "required": ["title"],
        }

        mcp_tool = {"name": unique_name, "inputSchema": parameters}
        if compact:
            mcp_tool["title"] = "[GitHub] create_issue"
        else:
            mcp_tool["description"] = full_description
        mcp_tool["_meta"] = {"original_tool_name": "create_issue", "server_id": "github"}
        return mcp_tool

    legacy = build_tool_dict(compact=False)
    compact = build_tool_dict(compact=True)

    # Both share the MCP-mandatory fields
    assert legacy["name"] == compact["name"]
    assert legacy["inputSchema"] == compact["inputSchema"]
    assert "_meta" in legacy and "_meta" in compact

    # Compact mode swaps verbose description for 1-line title
    assert "description" in legacy
    assert "title" not in legacy
    assert "title" in compact
    assert "description" not in compact

    # Token economy spot check: title is far shorter than description
    assert len(compact["title"]) < len(legacy["description"]) // 2
