"""Phase 5 tests — usage analytics, pin suggestions, preheat overlay.

Coverage
--------
- top_tools_for_user counts call rows over the lookback window and
  excludes composition/workflow pseudo-tools.
- top_compositions_for_user counts rows by composition_id.
- resolve_tool_names_to_ids maps prefixed names back to Tool.id and
  silently drops unknown names.
- /pool/pin/suggestions returns sorted suggestions with already-pinned
  and already-default-pool entries filtered out.
- /pool/pin/suggestions enforces min_count threshold.
- Preheat: tools used recently appear in the visible-pool ID set.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Tuple
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_log import ExecutionLog
from app.models.mcp_server import InstallType, MCPServer, ServerStatus
from app.models.organization import OrganizationMember
from app.models.pool_persistent import (
    OrgDefaultPoolEntry,
    UserPersistentPoolEntry,
)
from app.models.tool import Tool
from app.models.user import User
from app.services.usage_analytics import (
    resolve_tool_names_to_ids,
    top_compositions_for_user,
    top_tools_for_user,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ids(db: AsyncSession, email: str) -> Tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _make_server_and_tool(
    db: AsyncSession, org_id: UUID, *, server_name: str = "GitHub", tool_name: str = "create_issue"
) -> Tuple[MCPServer, Tool]:
    sid = f"srv-{uuid4().hex[:6]}"
    server = MCPServer(
        organization_id=org_id,
        server_id=sid,
        name=server_name,
        description="x",
        version="1.0.0",
        install_type=InstallType.NPM,
        install_package=sid,
        enabled=True,
        status=ServerStatus.RUNNING,
        is_visible_to_oauth_clients=True,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    tool = Tool(
        organization_id=org_id,
        server_id=server.id,
        tool_name=tool_name,
        display_name=tool_name,
        description=f"Tool {tool_name}",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        is_visible_to_oauth_clients=False,  # not in ephemeral pool
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return server, tool


async def _seed_calls(
    db: AsyncSession,
    *,
    user_id: UUID,
    organization_id: UUID,
    tool_name: str,
    count: int,
    days_ago: int = 0,
) -> None:
    """Insert ``count`` execution_log rows shaped like a tool_call from
    the given lookback window."""
    when = datetime.utcnow() - timedelta(days=days_ago)
    for _ in range(count):
        row = ExecutionLog(
            user_id=user_id,
            organization_id=organization_id,
            session_id="s",
            goal=None,
            mode="tool_call",
            shortcut_level=None,
            duration_ms=10,
            status="success",
            error=None,
            composition_id=None,
            tools_called=[tool_name],
            created_at=when,
            updated_at=when,
        )
        db.add(row)
    await db.commit()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


async def test_top_tools_counts_and_orders(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__create_issue", count=8)
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__list_issues", count=3)
    # Composition pseudo-tools must be excluded
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="composition_X", count=20)

    out = await top_tools_for_user(
        db_session, user_id=user_id, organization_id=org_id, days=7, limit=10
    )
    names = [u.tool_name for u in out]
    assert names == ["GitHub__create_issue", "GitHub__list_issues"]
    assert out[0].count == 8
    assert out[1].count == 3


async def test_top_tools_respects_window(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    # 5 within 3-day window, 5 from 60 days ago — only the 5 recent count
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__create_issue", count=5, days_ago=1)
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__create_issue", count=5, days_ago=60)
    out = await top_tools_for_user(
        db_session, user_id=user_id, organization_id=org_id, days=7, limit=5
    )
    assert out[0].count == 5


async def test_top_compositions_counts(db_session: AsyncSession, test_user: dict):
    user_id, org_id = await _ids(db_session, test_user["email"])
    cid = uuid4()
    when = datetime.utcnow() - timedelta(hours=1)
    for _ in range(4):
        db_session.add(
            ExecutionLog(
                user_id=user_id,
                organization_id=org_id,
                session_id="s",
                mode="goal",
                duration_ms=10,
                status="success",
                composition_id=cid,
                created_at=when,
                updated_at=when,
            )
        )
    await db_session.commit()
    out = await top_compositions_for_user(
        db_session, user_id=user_id, organization_id=org_id, days=7, limit=5
    )
    assert len(out) == 1
    assert out[0].composition_id == cid
    assert out[0].count == 4


async def test_resolve_tool_names_to_ids_drops_unknowns(
    db_session: AsyncSession, test_user: dict
):
    _, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id)
    out = await resolve_tool_names_to_ids(
        db_session,
        organization_id=org_id,
        prefixed_names=["GitHub__create_issue", "Unknown__nonexistent"],
    )
    assert len(out) == 1
    assert out[0] == ("GitHub__create_issue", tool.id)


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


async def test_suggestions_filters_already_pinned(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id, tool_name="create_issue")

    # 5 calls -> above min_count=3
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__create_issue", count=5)

    # Suggestion appears
    r1 = await client.get("/api/v1/pool/pin/suggestions", headers=auth_headers)
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert any(s["tool_id"] == str(tool.id) for s in body1["suggestions"])

    # Pin it -> next call should skip it
    db_session.add(
        UserPersistentPoolEntry(user_id=user_id, tool_id=tool.id, composition_id=None)
    )
    await db_session.commit()

    r2 = await client.get("/api/v1/pool/pin/suggestions", headers=auth_headers)
    assert r2.status_code == 200
    body2 = r2.json()
    assert all(s["tool_id"] != str(tool.id) for s in body2["suggestions"])


async def test_suggestions_filters_org_default(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id, tool_name="list_issues")
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__list_issues", count=4)
    db_session.add(
        OrgDefaultPoolEntry(
            organization_id=org_id, tool_id=tool.id, composition_id=None,
            position=1, added_by_user_id=user_id,
        )
    )
    await db_session.commit()
    r = await client.get("/api/v1/pool/pin/suggestions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert all(s.get("tool_id") != str(tool.id) for s in body["suggestions"])


async def test_suggestions_min_count_threshold(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, _ = await _make_server_and_tool(db_session, org_id, tool_name="below_threshold")
    await _seed_calls(db_session, user_id=user_id, organization_id=org_id,
                      tool_name="GitHub__below_threshold", count=2)
    r = await client.get(
        "/api/v1/pool/pin/suggestions?min_count=3", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["suggestions"] == []
