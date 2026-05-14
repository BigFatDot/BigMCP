"""End-to-end tests for the persistent pool overlays (Phase 3).

Coverage
--------
- Admin can add/list/remove org_default_pool entries; non-admin cannot.
- A non-admin user cannot mutate the default pool.
- ``tool_id`` XOR ``composition_id`` is enforced (400 if neither/both).
- Cross-org references are refused (403).
- Duplicate pin returns 409.
- ``load_visible_pool`` UNIONs ephemeral + org_default + user_pin.
- A tool that's only in org_default (is_visible_to_oauth_clients=False)
  still appears in the unioned pool.
- A user pin that overlaps with org_default doesn't double-emit.
- Audit trail (``instance.policy_changed`` with resource_type
  ``org_default_pool``) is emitted for admin add/remove.
"""

from __future__ import annotations

from typing import Tuple
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.composition import (
    Composition,
    CompositionStatus,
    CompositionVisibility,
)
from app.models.mcp_server import InstallType, MCPServer, ServerStatus
from app.models.organization import OrganizationMember
from app.models.pool_persistent import (
    OrgDefaultPoolEntry,
    UserPersistentPoolEntry,
)
from app.models.tool import Tool
from app.models.user import User
from app.routers.mcp_gateway.pool.pool_loader import load_visible_pool


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _promote(db: AsyncSession, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    prefs = dict(user.preferences or {})
    prefs["instance_admin"] = True
    user.preferences = prefs
    await db.commit()


async def _ids(db: AsyncSession, email: str) -> Tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _make_server_and_tool(
    db: AsyncSession,
    org_id: UUID,
    *,
    is_visible: bool = False,
    enabled: bool = True,
) -> Tuple[MCPServer, Tool]:
    sid = f"srv-{uuid4().hex[:6]}"
    server = MCPServer(
        organization_id=org_id,
        server_id=sid,
        name=sid,
        install_type=InstallType.NPM,
        install_package="@scope/test",
        enabled=enabled,
        is_visible_to_oauth_clients=is_visible,
        status=ServerStatus.STOPPED,
    )
    db.add(server)
    await db.flush()

    tool = Tool(
        organization_id=org_id,
        server_id=server.id,
        tool_name=f"tool_{uuid4().hex[:6]}",
        description="Test tool",
        parameters_schema={"type": "object", "properties": {}},
        is_visible_to_oauth_clients=is_visible,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(server)
    await db.refresh(tool)
    return server, tool


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


async def test_admin_can_add_list_remove_default_pool(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    user_id, org_id = await _ids(db_session, test_user["email"])
    _server, tool = await _make_server_and_tool(db_session, org_id)

    # Empty list
    initial = await client.get(
        "/api/v1/admin/org/default-pool", headers=auth_headers
    )
    assert initial.status_code == 200
    assert initial.json()["entries"] == []

    # Add one
    add = await client.post(
        "/api/v1/admin/org/default-pool",
        json={"tool_id": str(tool.id)},
        headers=auth_headers,
    )
    assert add.status_code == 201, add.text
    entry = add.json()
    assert entry["tool_id"] == str(tool.id)
    assert entry["composition_id"] is None
    assert entry["position"] == 1  # auto-assigned
    entry_id = entry["id"]

    # List shows it
    listing = await client.get(
        "/api/v1/admin/org/default-pool", headers=auth_headers
    )
    assert len(listing.json()["entries"]) == 1

    # Remove
    rm = await client.delete(
        f"/api/v1/admin/org/default-pool/{entry_id}", headers=auth_headers
    )
    assert rm.status_code == 204

    final = await client.get(
        "/api/v1/admin/org/default-pool", headers=auth_headers
    )
    assert final.json()["entries"] == []


async def test_non_admin_cannot_mutate_default_pool(
    client: AsyncClient, db_session: AsyncSession, test_user: dict
):
    # Register a 2nd, non-admin user
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "non-admin-pool@example.com",
            "password": "NotAdmin123!",
            "name": "Non Admin",
        },
    )
    assert register.status_code in (201, 202)
    await db_session.execute(
        update(User)
        .where(User.email == "non-admin-pool@example.com")
        .values(email_verified=True)
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "non-admin-pool@example.com", "password": "NotAdmin123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get("/api/v1/admin/org/default-pool", headers=headers)
    assert resp.status_code == 403


async def test_xor_constraint_enforced(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    # Both null
    none = await client.post(
        "/api/v1/admin/org/default-pool",
        json={},
        headers=auth_headers,
    )
    assert none.status_code == 400
    # Both set
    both = await client.post(
        "/api/v1/admin/org/default-pool",
        json={"tool_id": str(uuid4()), "composition_id": str(uuid4())},
        headers=auth_headers,
    )
    assert both.status_code == 400


async def test_cross_org_reference_refused(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])

    # Create another org with a tool we should NOT be able to reference
    from app.models.organization import Organization
    other_org = Organization(name="Other", slug="other")
    db_session.add(other_org)
    await db_session.commit()
    await db_session.refresh(other_org)

    _, other_tool = await _make_server_and_tool(db_session, other_org.id)

    resp = await client.post(
        "/api/v1/admin/org/default-pool",
        json={"tool_id": str(other_tool.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_audit_trail_for_default_pool_changes(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    await _promote(db_session, test_user["email"])
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id)

    add = await client.post(
        "/api/v1/admin/org/default-pool",
        json={"tool_id": str(tool.id)},
        headers=auth_headers,
    )
    entry_id = add.json()["id"]
    await client.delete(
        f"/api/v1/admin/org/default-pool/{entry_id}", headers=auth_headers
    )

    audits = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == AuditAction.POLICY_CHANGED.value)
            .where(AuditLog.resource_type == "org_default_pool")
        )
    ).scalars().all()
    operations = [a.details.get("operation") for a in audits]
    assert "add" in operations
    assert "remove" in operations


# ---------------------------------------------------------------------------
# User pin endpoints
# ---------------------------------------------------------------------------


async def test_user_can_pin_list_unpin(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id)

    initial = await client.get("/api/v1/pool/pin", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.json()["pins"] == []

    pin = await client.post(
        "/api/v1/pool/pin",
        json={"tool_id": str(tool.id)},
        headers=auth_headers,
    )
    assert pin.status_code == 201
    pin_id = pin.json()["id"]

    listing = await client.get("/api/v1/pool/pin", headers=auth_headers)
    assert len(listing.json()["pins"]) == 1

    unpin = await client.delete(
        f"/api/v1/pool/pin/{pin_id}", headers=auth_headers
    )
    assert unpin.status_code == 204

    final = await client.get("/api/v1/pool/pin", headers=auth_headers)
    assert final.json()["pins"] == []


async def test_duplicate_pin_returns_409(
    client: AsyncClient, db_session: AsyncSession, test_user: dict, auth_headers: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    _, tool = await _make_server_and_tool(db_session, org_id)
    first = await client.post(
        "/api/v1/pool/pin", json={"tool_id": str(tool.id)}, headers=auth_headers
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/pool/pin", json={"tool_id": str(tool.id)}, headers=auth_headers
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# load_visible_pool semantics
# ---------------------------------------------------------------------------


async def test_load_visible_pool_unions_three_layers(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])

    # Layer 1: ephemeral session pool (is_visible_to_oauth_clients=True)
    _server_a, tool_a = await _make_server_and_tool(
        db_session, org_id, is_visible=True
    )

    # Layer 2: org default pool (server visibility OFF — should still appear)
    _server_b, tool_b = await _make_server_and_tool(
        db_session, org_id, is_visible=False
    )
    db_session.add(
        OrgDefaultPoolEntry(
            organization_id=org_id, tool_id=tool_b.id, position=1
        )
    )
    await db_session.commit()

    # Layer 3: user pinned (also visibility OFF)
    _server_c, tool_c = await _make_server_and_tool(
        db_session, org_id, is_visible=False
    )
    db_session.add(
        UserPersistentPoolEntry(user_id=user_id, tool_id=tool_c.id)
    )
    await db_session.commit()

    pool = await load_visible_pool(db_session, org_id, user_id=user_id)
    tool_ids_in_pool = {e.id for e in pool if e.kind == "tool"}
    assert str(tool_a.id) in tool_ids_in_pool
    assert str(tool_b.id) in tool_ids_in_pool
    assert str(tool_c.id) in tool_ids_in_pool


async def test_load_visible_pool_dedup_overlapping_pin_and_default(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])

    _server, tool = await _make_server_and_tool(
        db_session, org_id, is_visible=False
    )
    db_session.add(
        OrgDefaultPoolEntry(
            organization_id=org_id, tool_id=tool.id, position=1
        )
    )
    db_session.add(
        UserPersistentPoolEntry(user_id=user_id, tool_id=tool.id)
    )
    await db_session.commit()

    pool = await load_visible_pool(db_session, org_id, user_id=user_id)
    matching = [e for e in pool if e.kind == "tool" and e.id == str(tool.id)]
    assert len(matching) == 1


async def test_load_visible_pool_includes_org_compositions(
    db_session: AsyncSession, test_user: dict
):
    user_id, org_id = await _ids(db_session, test_user["email"])
    comp = Composition(
        organization_id=org_id,
        created_by=user_id,
        name="my workflow",
        description="desc",
        visibility=CompositionVisibility.ORGANIZATION,
        status=CompositionStatus.PRODUCTION,
        steps=[],
        input_schema={"type": "object"},
    )
    db_session.add(comp)
    await db_session.commit()

    pool = await load_visible_pool(db_session, org_id, user_id=user_id)
    comp_entries = [e for e in pool if e.kind == "composition"]
    assert len(comp_entries) >= 1
    assert any(e.id == str(comp.id) for e in comp_entries)
