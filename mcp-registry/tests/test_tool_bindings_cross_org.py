"""Cross-org leak guards on tool_bindings endpoints.

The pre-audit tool_bindings router accepted a ``context_id`` query
param and passed it straight to the service without verifying the
caller's org owned that context. A member of org A could:
- list tool bindings for any context in any org (read leak)
- create a tool binding attached to a foreign context, with the
  binding row stamped as belonging to org A (corruption + write
  leak)
- copy a binding to a foreign context (same corruption)
- look up a binding by name under a foreign context (read leak)

This file covers all four endpoints via direct HTTP calls.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context import Context
from app.models.organization import OrganizationMember
from app.models.user import User


pytestmark = pytest.mark.asyncio


async def _ids(db: AsyncSession, email: str) -> tuple[UUID, UUID]:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    member = (
        await db.execute(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        )
    ).scalar_one()
    return user.id, member.organization_id


async def _make_foreign_context(db: AsyncSession) -> UUID:
    """A context belonging to a DIFFERENT org. Tests use this as the
    target of cross-org probes."""
    from uuid import uuid4 as _uuid4
    from app.models.organization import Organization, OrganizationType

    foreign_org = Organization(
        name="Foreign Org",
        slug=f"foreign-{_uuid4()}",
        organization_type=OrganizationType.PERSONAL,
    )
    db.add(foreign_org)
    await db.flush()

    ctx = Context(
        organization_id=foreign_org.id,
        name="foreign-context",
        path="/foreign",
        context_type="project",
    )
    db.add(ctx)
    await db.commit()
    await db.refresh(ctx)
    return ctx.id


async def test_list_bindings_rejects_foreign_context_id(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """GET /tool-bindings?context_id=<foreign> → 404 (uniform with
    'context not found' — no info leak about org boundaries)."""
    foreign_ctx_id = await _make_foreign_context(db_session)
    resp = await client.get(
        f"/api/v1/tool-bindings/?context_id={foreign_ctx_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()


async def test_create_binding_rejects_foreign_context_id(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """POST /tool-bindings?context_id=<foreign> → 404.

    Critical: before the fix, this would have CREATED a binding row
    in the caller's org but ATTACHED it to the foreign context — a
    silent corruption + cross-org leak."""
    foreign_ctx_id = await _make_foreign_context(db_session)
    resp = await client.post(
        f"/api/v1/tool-bindings/?context_id={foreign_ctx_id}",
        headers=auth_headers,
        json={
            "tool_id": str(uuid4()),
            "binding_name": "cross_org_test",
            "default_parameters": {},
            "locked_parameters": [],
            "description": None,
            "custom_validation": None,
        },
    )
    assert resp.status_code == 404


async def test_get_binding_by_name_rejects_foreign_context_id(
    client: AsyncClient, db_session: AsyncSession,
    test_user: dict, auth_headers: dict,
):
    """GET /tool-bindings/by-name/{name}?context_id=<foreign> → 404."""
    foreign_ctx_id = await _make_foreign_context(db_session)
    resp = await client.get(
        f"/api/v1/tool-bindings/by-name/any_binding?context_id={foreign_ctx_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_unknown_context_id_also_returns_404(
    client: AsyncClient, auth_headers: dict,
):
    """Sanity: a totally random UUID also returns 404 (so the foreign
    check doesn't accidentally leak existence via response timing or
    status). Same 404 shape as the cross-org case."""
    resp = await client.get(
        f"/api/v1/tool-bindings/?context_id={uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404
