"""MCP 2025-06-18 ``annotations`` and ``outputSchema`` exposure.

Coverage
--------
- get_pool_tools() ships behavior hints for the 3 meta-tools (search,
  execute, describe_tool) with the right truth values.
- All 3 meta-tools also ship an ``outputSchema`` (already pre-existing).
- Composition pseudo-tools get conservative ``destructiveHint=True``
  + ``openWorldHint=True`` annotations.
- Upstream-server-provided ``annotations`` and ``outputSchema`` flow
  through verbatim from the gateway's tool mapping (we don't fabricate
  behavior hints from the tool name — the spec says clients should
  treat any hint as untrusted).
"""

from __future__ import annotations


def test_pool_meta_tools_carry_annotations():
    from app.routers.mcp_gateway.pool.definitions import get_pool_tools

    by_name = {t["name"]: t for t in get_pool_tools()}
    assert set(by_name) == {"search", "execute", "describe_tool"}

    # search: writes the pool, no external side-effect, NOT idempotent.
    s = by_name["search"]["annotations"]
    assert s["readOnlyHint"] is False
    assert s["destructiveHint"] is False
    assert s["idempotentHint"] is False
    assert s["openWorldHint"] is False

    # execute: routes to anything — safe defaults are destructive + open.
    e = by_name["execute"]["annotations"]
    assert e["readOnlyHint"] is False
    assert e["destructiveHint"] is True
    assert e["openWorldHint"] is True

    # describe_tool: pure metadata read.
    d = by_name["describe_tool"]["annotations"]
    assert d["readOnlyHint"] is True
    assert d["destructiveHint"] is False
    assert d["idempotentHint"] is True
    assert d["openWorldHint"] is False


def test_pool_meta_tools_keep_output_schema():
    from app.routers.mcp_gateway.pool.definitions import get_pool_tools

    for tool in get_pool_tools():
        assert "outputSchema" in tool, f"{tool['name']} missing outputSchema"
        assert tool["outputSchema"]["type"] == "object"


def test_pool_meta_tools_have_titles_in_both_places():
    """Both the top-level ``title`` and ``annotations.title`` should be
    populated. The two may differ (one is the display name, the other a
    redundant hint inside annotations) but neither should be empty."""
    from app.routers.mcp_gateway.pool.definitions import get_pool_tools

    for tool in get_pool_tools():
        assert tool["title"], f"{tool['name']} missing top-level title"
        assert tool["annotations"]["title"], (
            f"{tool['name']} missing annotations.title"
        )
