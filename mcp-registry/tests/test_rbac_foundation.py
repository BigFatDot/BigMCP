"""Unit tests for the RBAC foundation in app.api.rbac.

Validates the pure logic (role hierarchy, effective role resolution,
cross-org guard). Integration tests covering the FastAPI dependency
itself live in ``test_rbac.py`` / ``test_scopes.py`` and will get the
``require_admin``/`require_member`-based fixtures in a follow-up
phase, after the first endpoints are migrated.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.rbac import (
    ROLE_HIERARCHY,
    AuthContext,
    RoleLevel,
    assert_resource_in_org,
    get_effective_role,
    require_admin,
    require_member,
    require_owner,
    require_viewer,
)
from app.models.organization import UserRole


# ---------------------------------------------------------------------------
# Lightweight fakes — we don't need real SQLAlchemy instances for the
# pure-logic tests. The dependency-injection layer is tested in the
# integration suite where Depends() can actually run.
# ---------------------------------------------------------------------------


class _FakeMembership:
    def __init__(self, role, organization_id):
        self.role = role
        self.organization_id = organization_id


class _FakeUser:
    def __init__(self, *, preferences=None, memberships=None):
        self.id = uuid4()
        self.preferences = preferences
        self.organization_memberships = memberships or []


# ---------------------------------------------------------------------------
# RoleLevel hierarchy
# ---------------------------------------------------------------------------


def test_role_level_strict_hierarchy():
    """OWNER > ADMIN > MEMBER > VIEWER, comparable as integers."""
    assert RoleLevel.OWNER > RoleLevel.ADMIN
    assert RoleLevel.ADMIN > RoleLevel.MEMBER
    assert RoleLevel.MEMBER > RoleLevel.VIEWER


def test_role_hierarchy_maps_all_user_roles():
    """Every UserRole must map to a RoleLevel — fail loud on missing roles."""
    for role in UserRole:
        assert role.value in ROLE_HIERARCHY, f"UserRole.{role.name} missing"


# ---------------------------------------------------------------------------
# get_effective_role — non-instance-admin paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_role,expected_level",
    [
        (UserRole.OWNER, RoleLevel.OWNER),
        (UserRole.ADMIN, RoleLevel.ADMIN),
        (UserRole.MEMBER, RoleLevel.MEMBER),
        (UserRole.VIEWER, RoleLevel.VIEWER),
    ],
)
def test_effective_role_for_each_membership(user_role, expected_level):
    org = uuid4()
    user = _FakeUser(memberships=[_FakeMembership(user_role, org)])
    level, override = get_effective_role(user, org)
    assert level == expected_level
    assert override is False


def test_effective_role_no_membership_returns_none():
    user = _FakeUser(memberships=[])
    level, override = get_effective_role(user, uuid4())
    assert level is None
    assert override is False


def test_effective_role_wrong_org_membership_returns_none():
    """User is member of org A but asks about org B — no access."""
    org_a, org_b = uuid4(), uuid4()
    user = _FakeUser(memberships=[_FakeMembership(UserRole.OWNER, org_a)])
    level, override = get_effective_role(user, org_b)
    assert level is None
    assert override is False


# ---------------------------------------------------------------------------
# get_effective_role — instance-admin paths (the super-role)
# ---------------------------------------------------------------------------


def test_effective_role_instance_admin_no_membership_is_override():
    """Instance admin with no membership in org X: OWNER + override flag."""
    org = uuid4()
    user = _FakeUser(preferences={"instance_admin": True}, memberships=[])
    level, override = get_effective_role(user, org)
    assert level == RoleLevel.OWNER
    assert override is True


def test_effective_role_instance_admin_member_role_elevated():
    """Instance admin who's only a MEMBER: elevated to OWNER + override."""
    org = uuid4()
    user = _FakeUser(
        preferences={"instance_admin": True},
        memberships=[_FakeMembership(UserRole.MEMBER, org)],
    )
    level, override = get_effective_role(user, org)
    assert level == RoleLevel.OWNER
    assert override is True


def test_effective_role_instance_admin_natural_owner_no_override():
    """Instance admin who IS already OWNER: no override needed."""
    org = uuid4()
    user = _FakeUser(
        preferences={"instance_admin": True},
        memberships=[_FakeMembership(UserRole.OWNER, org)],
    )
    level, override = get_effective_role(user, org)
    assert level == RoleLevel.OWNER
    assert override is False


def test_effective_role_instance_admin_flag_missing_treated_as_false():
    """preferences exists but doesn't have instance_admin key → regular user."""
    org = uuid4()
    user = _FakeUser(
        preferences={"other_pref": "value"},
        memberships=[_FakeMembership(UserRole.MEMBER, org)],
    )
    level, override = get_effective_role(user, org)
    assert level == RoleLevel.MEMBER
    assert override is False


def test_effective_role_instance_admin_flag_false_treated_as_false():
    """instance_admin=false explicitly → regular user."""
    org = uuid4()
    user = _FakeUser(
        preferences={"instance_admin": False},
        memberships=[_FakeMembership(UserRole.ADMIN, org)],
    )
    level, override = get_effective_role(user, org)
    assert level == RoleLevel.ADMIN
    assert override is False


def test_effective_role_instance_admin_no_preferences_attr_safe():
    """preferences=None should not crash."""
    user = _FakeUser(preferences=None, memberships=[])
    level, override = get_effective_role(user, uuid4())
    assert level is None
    assert override is False


# ---------------------------------------------------------------------------
# assert_resource_in_org — cross-org leak guard
# ---------------------------------------------------------------------------


def test_assert_resource_in_org_match_passes():
    org = uuid4()
    # Should not raise.
    assert_resource_in_org(org, org)


def test_assert_resource_in_org_mismatch_raises_404():
    """Mismatch → 404 (not 403) to avoid enumeration of foreign-org IDs."""
    with pytest.raises(HTTPException) as excinfo:
        assert_resource_in_org(uuid4(), uuid4(), "composition")
    assert excinfo.value.status_code == 404
    assert "composition not found" in excinfo.value.detail.lower()


def test_assert_resource_in_org_default_label():
    """The default 'resource' label is used when none provided."""
    with pytest.raises(HTTPException) as excinfo:
        assert_resource_in_org(uuid4(), uuid4())
    assert "resource not found" in excinfo.value.detail.lower()


# ---------------------------------------------------------------------------
# Factory aliases — sanity that the four common cases exist and are
# distinct callables (we can't easily test the full dependency chain
# here, it needs the integration suite with a real FastAPI app).
# ---------------------------------------------------------------------------


def test_require_role_aliases_are_distinct_callables():
    assert callable(require_viewer)
    assert callable(require_member)
    assert callable(require_admin)
    assert callable(require_owner)
    # Each factory call returns a new closure, so they're not identical.
    assert require_viewer is not require_member
    assert require_admin is not require_owner


# ---------------------------------------------------------------------------
# AuthContext shape — frozen + carries everything endpoints need
# ---------------------------------------------------------------------------


def test_auth_context_is_frozen():
    """AuthContext is frozen so endpoints can't accidentally mutate it."""
    user = _FakeUser()
    ctx = AuthContext(
        user=user,
        organization_id=uuid4(),
        role_level=RoleLevel.ADMIN,
        is_instance_override=False,
    )
    with pytest.raises((AttributeError, Exception)):
        ctx.role_level = RoleLevel.OWNER
