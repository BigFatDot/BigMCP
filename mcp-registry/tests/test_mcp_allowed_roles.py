"""Tests for MCPServer.allowed_roles RBAC (N2.3).

The runtime filter lives in the MCP gateway's
``_get_user_configured_servers`` and is hard to spin up in isolation
(touches Redis, the user-server pool, marketplace caches…). These
tests cover the contract directly:

- model accepts and persists allowed_roles
- the convention "empty list = all except viewer" matches Composition
- non-empty list is a strict whitelist (case-insensitive)
- update endpoint validates roles against the UserRole enum
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import InstallType, MCPServer
from app.models.organization import Organization, OrganizationType, UserRole
from app.services.mcp_server_service import MCPServerService


def _role_allowed(allowed_roles: list[str] | None, user_role: str) -> bool:
    """Reproduce the lambda used in mcp_unified.py for unit testing."""
    if not allowed_roles:
        return user_role != UserRole.VIEWER.value
    return user_role.lower() in {r.lower() for r in allowed_roles}


# ---------------------------------------------------------------------------
# Convention sanity (no DB)
# ---------------------------------------------------------------------------


def test_empty_list_means_all_except_viewer():
    for role in (UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER):
        assert _role_allowed([], role.value) is True
    assert _role_allowed([], UserRole.VIEWER.value) is False


def test_non_empty_list_is_strict_whitelist():
    assert _role_allowed(["admin"], UserRole.ADMIN.value) is True
    assert _role_allowed(["admin"], UserRole.OWNER.value) is False
    assert _role_allowed(["admin", "owner"], UserRole.OWNER.value) is True
    assert _role_allowed(["viewer"], UserRole.VIEWER.value) is True
    assert _role_allowed(["VIEWER"], UserRole.VIEWER.value) is True  # case-insensitive
    assert _role_allowed(["member"], UserRole.OWNER.value) is False


# ---------------------------------------------------------------------------
# Model persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_server_persists_allowed_roles(db_session: AsyncSession):
    org = Organization(
        name="Persistence Org",
        slug=f"persist-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        organization_id=org.id,
        server_id=f"srv-{uuid4().hex[:8]}",
        name="rbac-server",
        install_type=InstallType.NPM,
        allowed_roles=["admin"],
    )
    db_session.add(server)
    await db_session.commit()

    reloaded = (
        await db_session.execute(select(MCPServer).where(MCPServer.id == server.id))
    ).scalar_one()
    assert reloaded.allowed_roles == ["admin"]


# ---------------------------------------------------------------------------
# Service-level: update_config rejects unknown role values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_config_rejects_unknown_role(db_session: AsyncSession):
    org = Organization(
        name="Validate Org",
        slug=f"validate-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        organization_id=org.id,
        server_id=f"srv-{uuid4().hex[:8]}",
        name="rbac-server",
        install_type=InstallType.NPM,
    )
    db_session.add(server)
    await db_session.commit()

    svc = MCPServerService(db_session)
    with pytest.raises(ValueError, match="Invalid role 'janitor'"):
        await svc.update_config(server_id=server.id, allowed_roles=["janitor"])

    # Service must accept canonical roles (case-insensitive on input,
    # stored lowercased).
    updated = await svc.update_config(
        server_id=server.id, allowed_roles=["ADMIN", "Owner"]
    )
    assert updated.allowed_roles == ["admin", "owner"]


@pytest.mark.asyncio
async def test_update_config_empty_list_clears_restriction(db_session: AsyncSession):
    org = Organization(
        name="Clear Org",
        slug=f"clear-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
    )
    db_session.add(org)
    await db_session.flush()

    server = MCPServer(
        organization_id=org.id,
        server_id=f"srv-{uuid4().hex[:8]}",
        name="rbac-server",
        install_type=InstallType.NPM,
        allowed_roles=["admin"],
    )
    db_session.add(server)
    await db_session.commit()

    svc = MCPServerService(db_session)
    updated = await svc.update_config(server_id=server.id, allowed_roles=[])
    assert updated.allowed_roles == []
