"""
Unit tests for the `execute` MCP tool handler — pure logic only.

DB-touching paths (pool loading, single-tool routing, full orchestration)
are exercised by the integration suite in Phase 6.1.
"""

import pytest

from app.routers.mcp_gateway.pool.execute_handler import (
    _L2_MIN_GAP,
    _L2_MIN_TOP_SCORE,
    _sanitize_server_prefix,
    _score_pool_against_goal,
    handle_execute,
)


class _FakeTool:
    def __init__(self, tool_name, description="", display_name=None, tags=None, category=None):
        self.tool_name = tool_name
        self.description = description
        self.display_name = display_name
        self.tags = tags
        self.category = category


class _FakeServer:
    def __init__(self, name):
        self.name = name


def test_sanitize_server_prefix_replaces_special_chars():
    assert _sanitize_server_prefix("Hostinger DNS") == "Hostinger_DNS"
    assert _sanitize_server_prefix("foo--bar!!") == "foo_bar"
    assert _sanitize_server_prefix("") == ""


def test_score_pool_against_goal_orders_by_score():
    pool = [
        (_FakeTool("send_email", description="Sends an email"), _FakeServer("Mail")),
        (_FakeTool("create_dns_record", description="Creates a DNS record"), _FakeServer("Hostinger")),
    ]
    scored = _score_pool_against_goal("create dns record on hostinger", pool)
    # First should be the DNS one, by name match.
    assert scored[0][1].tool_name == "create_dns_record"
    assert scored[0][0] > scored[1][0]


def test_l2_thresholds_are_conservative():
    """Sanity-check that the shortcut thresholds are not too lax.

    A single token match (score 1 in haystack only) should never trigger L2.
    """
    pool = [
        (_FakeTool("send_email", description="emails"), _FakeServer("Mail")),
        (_FakeTool("send_sms", description="texts"), _FakeServer("SMS")),
    ]
    scored = _score_pool_against_goal("send", pool)
    top1 = scored[0]
    runner_up = scored[1][0] if len(scored) >= 2 else 0
    triggers_l2 = top1[0] >= _L2_MIN_TOP_SCORE and (top1[0] - runner_up) >= _L2_MIN_GAP
    # Both tools have "send" in name → tie or near-tie, must NOT trigger L2.
    assert not triggers_l2


@pytest.mark.asyncio
async def test_handle_execute_rejects_no_action():
    result = await handle_execute(
        {}, user_id="u", organization_id="o", gateway=None
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_handle_execute_requires_auth():
    result = await handle_execute(
        {"goal": "do something"},
        user_id=None,
        organization_id=None,
        gateway=None,
    )
    assert "error" in result and "auth" in result["error"].lower()


@pytest.mark.asyncio
async def test_handle_execute_rejects_invalid_params_type():
    result = await handle_execute(
        {"goal": "x", "params": "not a dict"},
        user_id="u",
        organization_id="o",
        gateway=None,
    )
    assert "error" in result
    assert "params" in result["error"].lower()
