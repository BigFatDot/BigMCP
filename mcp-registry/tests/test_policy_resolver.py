"""Tests for PolicyResolver — the instance/org policy composition engine.

Validates the monotone-decreasing composition contract that underpins
N1.1 of the access-control roadmap. The whole point of these tests is
to make it impossible for an org-level override to relax an instance
policy.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instance_settings import InstanceSettings
from app.models.organization import Organization, OrganizationType
from app.schemas.policy import (
    ClientControlPolicy,
    intersect_lists,
    stricter_dcr,
)
from app.services.policy_resolver import PolicyResolver


# ---------------------------------------------------------------------------
# Pure helpers — no DB needed.
# ---------------------------------------------------------------------------


def test_stricter_dcr_orders_correctly():
    assert stricter_dcr("open", "open") == "open"
    assert stricter_dcr("open", "admin_approval") == "admin_approval"
    assert stricter_dcr("admin_approval", "denied") == "denied"
    assert stricter_dcr("denied", "open") == "denied"


def test_intersect_lists_org_can_shrink_only():
    # Instance allows A, B; org tries to allow C — C is dropped.
    assert intersect_lists(["A", "B"], ["B", "C"]) == ["B"]

    # Instance whitelist empty == "any allowed"; org override wins as-is.
    assert intersect_lists([], ["A"]) == ["A"]

    # Org keeps everything if no override.
    assert intersect_lists(["A"], None) == ["A"]

    # Both empty → empty.
    assert intersect_lists([], None) == []


# ---------------------------------------------------------------------------
# env_defaults() — purely synchronous.
# ---------------------------------------------------------------------------


def test_env_defaults_returns_safe_baseline(db_session: AsyncSession):
    resolver = PolicyResolver(db_session)
    pol = resolver.env_defaults()
    assert isinstance(pol, ClientControlPolicy)
    # Defaults must be permissive enough to not break existing setups.
    assert pol.dcr_policy == "open"
    assert pol.require_cimd is False
    assert pol.trusted_cimd_urls == []
    assert pol.auto_approve_cimd is True


# ---------------------------------------------------------------------------
# Instance layer — no row vs stored row.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_instance_policy_falls_back_to_env_defaults(
    db_session: AsyncSession,
):
    """With no InstanceSettings row, the resolver returns env defaults."""
    resolver = PolicyResolver(db_session)
    pol = await resolver.get_instance_policy()
    assert pol.dcr_policy == "open"
    assert pol.require_cimd is False


@pytest.mark.asyncio
async def test_get_instance_policy_layers_stored_over_defaults(
    db_session: AsyncSession,
):
    """A stored field overrides its env default; missing keys still default."""
    db_session.add(
        InstanceSettings(
            id=1,
            client_control={"dcr_policy": "admin_approval", "require_cimd": True},
        )
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.get_instance_policy()
    assert pol.dcr_policy == "admin_approval"
    assert pol.require_cimd is True
    # Unset keys keep env defaults.
    assert pol.auto_approve_cimd is True


# ---------------------------------------------------------------------------
# Effective policy — instance ⋂ org composition.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_without_org_returns_instance_policy(
    db_session: AsyncSession,
):
    """A None organization_id (instance-wide context) skips composition."""
    db_session.add(
        InstanceSettings(id=1, client_control={"dcr_policy": "denied"})
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(None)
    assert pol.dcr_policy == "denied"


@pytest.mark.asyncio
async def test_resolve_with_org_no_override_returns_instance_policy(
    db_session: AsyncSession,
):
    org = Organization(name="No-override Org", slug=f"no-override-{uuid4().hex[:8]}",
                       organization_type=OrganizationType.TEAM, settings={})
    db_session.add(org)
    db_session.add(
        InstanceSettings(id=1, client_control={"dcr_policy": "admin_approval"})
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    assert pol.dcr_policy == "admin_approval"


@pytest.mark.asyncio
async def test_org_cannot_relax_instance_require_cimd(
    db_session: AsyncSession,
):
    """Critical invariant: org cannot turn off instance's require_cimd."""
    org = Organization(
        name="Relaxing Org", slug=f"relax-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
        settings={"client_control": {"require_cimd": False}},
    )
    db_session.add(org)
    db_session.add(
        InstanceSettings(id=1, client_control={"require_cimd": True})
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    # Org override is IGNORED — instance's True wins.
    assert pol.require_cimd is True


@pytest.mark.asyncio
async def test_org_can_strengthen_dcr_policy(
    db_session: AsyncSession,
):
    """Org can move from instance.open → org.admin_approval (stricter)."""
    org = Organization(
        name="Stricter Org", slug=f"stricter-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
        settings={"client_control": {"dcr_policy": "admin_approval"}},
    )
    db_session.add(org)
    db_session.add(
        InstanceSettings(id=1, client_control={"dcr_policy": "open"})
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    assert pol.dcr_policy == "admin_approval"


@pytest.mark.asyncio
async def test_org_cannot_weaken_dcr_policy(
    db_session: AsyncSession,
):
    """Org with dcr_policy=open cannot relax instance's denied."""
    org = Organization(
        name="Relax Org", slug=f"relax-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
        settings={"client_control": {"dcr_policy": "open"}},
    )
    db_session.add(org)
    db_session.add(
        InstanceSettings(id=1, client_control={"dcr_policy": "denied"})
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    # Instance's denied wins.
    assert pol.dcr_policy == "denied"


@pytest.mark.asyncio
async def test_trusted_cimd_urls_are_intersected(
    db_session: AsyncSession,
):
    """Org whitelist can only ever be a subset of instance whitelist."""
    org = Organization(
        name="CIMD Org", slug=f"cimd-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
        settings={
            "client_control": {
                "trusted_cimd_urls": [
                    "https://claude.ai/.well-known/cimd",
                    "https://evil.example/cimd",  # not in instance — must drop
                ]
            }
        },
    )
    db_session.add(org)
    db_session.add(
        InstanceSettings(
            id=1,
            client_control={
                "trusted_cimd_urls": [
                    "https://claude.ai/.well-known/cimd",
                    "https://cursor.sh/.well-known/cimd",
                ]
            },
        )
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    assert pol.trusted_cimd_urls == ["https://claude.ai/.well-known/cimd"]


@pytest.mark.asyncio
async def test_auto_approve_is_and(db_session: AsyncSession):
    """If either side disables auto_approve, the effective policy disables it."""
    org = Organization(
        name="No-AutoApprove", slug=f"nope-{uuid4().hex[:8]}",
        organization_type=OrganizationType.TEAM,
        settings={"client_control": {"auto_approve_cimd": False}},
    )
    db_session.add(org)
    db_session.add(
        InstanceSettings(
            id=1, client_control={"auto_approve_cimd": True}  # instance OK
        )
    )
    await db_session.commit()

    resolver = PolicyResolver(db_session)
    pol = await resolver.resolve_effective_policy(org.id)
    assert pol.auto_approve_cimd is False
