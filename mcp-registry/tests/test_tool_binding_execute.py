"""Tool binding execute pipeline (real MCP routing via UserServerPool).

The /execute endpoint used to return a hard-coded placeholder. Now it
routes through ``gateway.user_server_pool.get_or_start_server`` +
``wrapper.call_tool``. These tests pin that contract:

- success path: pool is asked for the right (user, server) pair,
  wrapper.call_tool is invoked with the merged params, and the MCP
  result is propagated back through the HTTP response.
- failure path: when the pool refuses to start the server (e.g.
  server not configured for the user, install failed, transport
  unreachable), the endpoint returns success=False with an error
  message — no placeholder leaks.

The pool is patched at the import site used by the service
(``app.routers.mcp_unified.gateway.user_server_pool``) so we don't
need to actually boot any MCP subprocess.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import Context
from app.models.mcp_server import MCPServer, InstallType, ServerStatus
from app.models.organization import OrganizationMember
from app.models.tool import Tool, ToolBinding
from app.models.user import User


pytestmark = pytest.mark.asyncio


async def _user_and_org(db: AsyncSession, email: str) -> tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _seed_binding(
    db: AsyncSession,
    organization_id: UUID,
    *,
    tool_name: str = "create_document",
    default_parameters: Dict[str, Any] | None = None,
    locked_parameters: list[str] | None = None,
    parameters_schema: Dict[str, Any] | None = None,
) -> tuple[ToolBinding, MCPServer, Tool, Context]:
    """Build a minimal context → server → tool → binding chain."""
    ctx = Context(
        organization_id=organization_id,
        name="exec-test-ctx",
        path="/exec-test",
        context_type="project",
    )
    db.add(ctx)
    await db.flush()

    server = MCPServer(
        organization_id=organization_id,
        server_id="mock-server",
        name="Mock Server",
        install_type=InstallType.NPM if hasattr(InstallType, "NPM") else "npm",
        install_package="@mock/server",
        command="npx",
        args=["-y", "@mock/server"],
        env={},
        status=ServerStatus.STOPPED,
    )
    db.add(server)
    await db.flush()

    tool = Tool(
        organization_id=organization_id,
        server_id=server.id,
        tool_name=tool_name,
        display_name=tool_name,
        description="test tool",
        parameters_schema=parameters_schema
        or {
            "type": "object",
            "properties": {
                "base_url": {"type": "string"},
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["title"],
        },
    )
    db.add(tool)
    await db.flush()

    binding = ToolBinding(
        organization_id=organization_id,
        context_id=ctx.id,
        tool_id=tool.id,
        binding_name="create_doc",
        default_parameters=default_parameters
        or {"base_url": "https://docs.example", "project_id": "p-1"},
        locked_parameters=locked_parameters or ["base_url", "project_id"],
        custom_validation=None,
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    await db.refresh(server)
    await db.refresh(tool)
    return binding, server, tool, ctx


def _patch_pool(monkeypatch, *, wrapper_result: Any = None, start_exc: Exception | None = None,
                call_exc: Exception | None = None) -> MagicMock:
    """Patch ``gateway.user_server_pool`` with an in-memory fake.

    Returns the pool mock so tests can assert call args.
    """
    from app.routers import mcp_unified

    wrapper = MagicMock()
    if call_exc:
        wrapper.call_tool = AsyncMock(side_effect=call_exc)
    else:
        wrapper.call_tool = AsyncMock(return_value=wrapper_result)

    pool = MagicMock()
    if start_exc:
        pool.get_or_start_server = AsyncMock(side_effect=start_exc)
    else:
        pool.get_or_start_server = AsyncMock(return_value=wrapper)

    fake_gateway = MagicMock()
    fake_gateway.user_server_pool = pool

    monkeypatch.setattr(mcp_unified, "gateway", fake_gateway)
    return pool


async def test_execute_binding_routes_to_pool_and_returns_real_result(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
    monkeypatch,
):
    """Happy path: POST /tool-bindings/{id}/execute drives the
    UserServerPool and propagates the wrapper's response."""
    user_id, org_id = await _user_and_org(db_session, "testuser@example.com")
    binding, server, tool, _ctx = await _seed_binding(db_session, org_id)

    mcp_payload = {
        "content": [{"type": "text", "text": '{"document_id":"doc-123"}'}],
        "isError": False,
    }
    pool = _patch_pool(monkeypatch, wrapper_result=mcp_payload)

    resp = await client.post(
        f"/api/v1/tool-bindings/{binding.id}/execute",
        headers=auth_headers,
        json={"parameters": {"title": "Meeting Notes", "content": "..."}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Real wrapper result propagated, NOT the placeholder.
    assert body["success"] is True
    assert body["error"] is None
    assert body["result"] == mcp_payload
    assert body["tool_name"] == "create_document"
    # ToolBinding default + locked params were merged with user params
    assert body["merged_parameters"] == {
        "base_url": "https://docs.example",
        "project_id": "p-1",
        "title": "Meeting Notes",
        "content": "...",
    }

    # Pool was asked to start the server for the CALLER (multi-tenant
    # isolation: never the server's own org if the caller has another).
    pool.get_or_start_server.assert_awaited_once()
    kwargs = pool.get_or_start_server.await_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["server_id"] == server.id
    assert kwargs["organization_id"] == org_id

    # And the wrapper was invoked with the NATIVE tool name
    # (not the gateway-prefixed display name) + merged params.
    wrapper = await pool.get_or_start_server.__wrapped__(  # type: ignore[attr-defined]
        user_id, server.id, org_id
    ) if hasattr(pool.get_or_start_server, "__wrapped__") else None
    # Direct assertion on the wrapper recorded inside the AsyncMock:
    wrapper_mock = pool.get_or_start_server.return_value
    wrapper_mock.call_tool.assert_awaited_once_with(
        "create_document",
        {
            "base_url": "https://docs.example",
            "project_id": "p-1",
            "title": "Meeting Notes",
            "content": "...",
        },
    )


async def test_execute_binding_returns_error_when_pool_cannot_start_server(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: dict,
    auth_headers: dict,
    monkeypatch,
):
    """Failure path: if get_or_start_server raises (e.g. the server
    can't be installed, no credentials configured, upstream HTTP
    server unreachable), the endpoint returns 200 with success=False
    and a non-empty error message — NOT the placeholder, and NOT a
    500 (the binding itself is fine, the execution is what failed)."""
    _user_id, org_id = await _user_and_org(db_session, "testuser@example.com")
    binding, _server, _tool, _ctx = await _seed_binding(db_session, org_id)

    _patch_pool(
        monkeypatch,
        start_exc=RuntimeError("Failed to install server package for mock-server"),
    )

    resp = await client.post(
        f"/api/v1/tool-bindings/{binding.id}/execute",
        headers=auth_headers,
        json={"parameters": {"title": "x"}},
    )
    # The router converts RuntimeError raised by the service into a
    # success=False response (HTTP 200) carrying the error string. This
    # is the existing contract used by every other binding execution
    # path; we only assert the error is surfaced (no placeholder).
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error"], "error message must be propagated"
    # The placeholder string must NEVER appear anymore.
    assert "placeholder" not in (body.get("error") or "").lower()
    assert "placeholder" not in str(body.get("result") or "").lower()
