"""
RBAC foundation for org-scoped operations.

Unified authorization model :

  Strict role hierarchy :  OWNER > ADMIN > MEMBER > VIEWER
  Instance admin       :   super-role that supersedes ANY org role.

This module is **additive** : it does not replace the existing helpers
(`require_instance_admin` in ``dependencies.py``, ``require_org_admin``
inline in ``organizations.py``, ``get_current_admin_user``). Endpoints
migrate at their own pace by switching to the typed
``Depends(require_admin)`` style.

Usage in an endpoint :

    from ..rbac import require_admin, AuthContext

    @router.post("/")
    async def create_thing(
        payload: ThingCreate,
        auth: AuthContext = Depends(require_admin),
    ):
        # auth.user / auth.organization_id / auth.role_level
        # auth.is_instance_override  (True if instance_admin acted on
        #                             an org they're not a normal admin of)
        ...

Cross-org guard pattern (use AFTER loading a resource by id) :

    from ..rbac import assert_resource_in_org

    composition = await db.get(Composition, comp_id)
    if composition is None:
        raise HTTPException(404)
    assert_resource_in_org(composition.organization_id, auth.organization_id, "composition")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Awaitable, Callable, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_async_session
from ..models.audit_log import AuditAction
from ..models.organization import OrganizationMember, UserRole
from ..models.user import User
from .dependencies import (
    get_current_organization_jwt,
    get_current_user_jwt,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------


class RoleLevel(IntEnum):
    """Strict org role hierarchy. Higher number = broader permissions.

    Intentionally a closed enum mapping the existing ``UserRole`` enum
    string values. We use IntEnum so dependencies can express
    ``min_level=RoleLevel.ADMIN`` and compare with ``>=`` naturally.
    """

    VIEWER = 1
    MEMBER = 2
    ADMIN = 3
    OWNER = 4


# Map the persisted string role to its hierarchy level. We key on the
# str ``value`` of the existing ``UserRole`` enum so this works
# regardless of how the row was loaded (enum instance vs raw string).
ROLE_HIERARCHY: dict[str, RoleLevel] = {
    UserRole.VIEWER.value: RoleLevel.VIEWER,
    UserRole.MEMBER.value: RoleLevel.MEMBER,
    UserRole.ADMIN.value: RoleLevel.ADMIN,
    UserRole.OWNER.value: RoleLevel.OWNER,
}


def _role_to_level(role) -> Optional[RoleLevel]:
    """Resolve a ``UserRole`` instance OR its string value to a level."""
    if role is None:
        return None
    value = role.value if hasattr(role, "value") else role
    return ROLE_HIERARCHY.get(value)


# ---------------------------------------------------------------------------
# Auth context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthContext:
    """Resolved authentication + authorization context for one request.

    Returned by every ``require_role`` dependency so endpoints don't
    need to re-fetch the membership or recompute the role level.
    """

    user: User
    organization_id: UUID
    role_level: RoleLevel
    is_instance_override: bool
    """True when the effective role comes from the instance-admin override
    rather than a real org membership at that level. Audit-logged at the
    call site. Useful for endpoints that want to know they're operating
    on a foreign org (e.g., to add extra logging or rate-limit)."""


# ---------------------------------------------------------------------------
# Effective role resolution
# ---------------------------------------------------------------------------


def _is_instance_admin(user: User) -> bool:
    return bool(
        user.preferences
        and isinstance(user.preferences, dict)
        and user.preferences.get("instance_admin") is True
    )


def get_effective_role(
    user: User, organization_id: UUID
) -> tuple[Optional[RoleLevel], bool]:
    """Resolve the user's effective role in the given org.

    Returns ``(level, is_override)``:
    - **instance admin**: implicit OWNER on any org. ``is_override=True``
      when the user has no real membership OR has a lower role than
      OWNER in this org (the override "elevates" them).
    - **org member**: the role level corresponding to their stored role.
      ``is_override=False``.
    - **non-member, non-instance-admin**: returns ``(None, False)``.

    Does not raise — callers decide whether ``None`` is a 403 or fall-through.
    """
    membership: Optional[OrganizationMember] = None
    for m in user.organization_memberships or []:
        if m.organization_id == organization_id:
            membership = m
            break

    if _is_instance_admin(user):
        # Super-role: instance admin gets implicit OWNER everywhere.
        if membership is None:
            return RoleLevel.OWNER, True  # pure override (no real membership)
        actual = _role_to_level(membership.role)
        if actual is None or actual < RoleLevel.OWNER:
            return RoleLevel.OWNER, True  # elevated by override
        return actual, False  # naturally OWNER, no override needed

    if membership is None:
        return None, False

    return _role_to_level(membership.role), False


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


async def _audit_deny(
    user: User,
    organization_id: UUID,
    required: RoleLevel,
    actual: Optional[RoleLevel],
    db: AsyncSession,
) -> None:
    """Best-effort audit log entry on RBAC deny. Never raises."""
    try:
        from ..services.audit_service import AuditService

        await AuditService(db).log_action(
            action=AuditAction.AUTHORIZATION_DENIED,
            actor_id=user.id,
            organization_id=organization_id,
            details={
                "required_role": required.name,
                "actual_role": actual.name if actual else None,
            },
        )
    except Exception:  # pragma: no cover — audit must never block the response
        logger.exception("Failed to write AUTHORIZATION_DENIED audit row")


async def _audit_instance_override(
    user: User,
    organization_id: UUID,
    required: RoleLevel,
    db: AsyncSession,
) -> None:
    """Audit a successful action that relied on the instance-admin override."""
    try:
        from ..services.audit_service import AuditService

        await AuditService(db).log_action(
            action=AuditAction.CROSS_ORG_INSTANCE_OVERRIDE,
            actor_id=user.id,
            organization_id=organization_id,
            details={"required_role": required.name},
        )
    except Exception:  # pragma: no cover
        logger.exception(
            "Failed to write CROSS_ORG_INSTANCE_OVERRIDE audit row"
        )


# ---------------------------------------------------------------------------
# Dependency factory
# ---------------------------------------------------------------------------


def require_role(min_level: RoleLevel) -> Callable[..., Awaitable[AuthContext]]:
    """Build a FastAPI dependency that requires ``>= min_level`` in the
    JWT-resolved org context.

    Returns an ``AuthContext`` so endpoints get the (user, org_id, level,
    is_instance_override) tuple without re-fetching anything.

    Resolution order matches the rest of the app — JWT ``org_id`` claim
    wins, fall back to single membership, 400 if ambiguous.
    """

    async def dep(
        user: User = Depends(get_current_user_jwt),
        org_context: tuple[OrganizationMember, UUID] = Depends(
            get_current_organization_jwt
        ),
        db: AsyncSession = Depends(get_async_session),
    ) -> AuthContext:
        _, organization_id = org_context
        level, is_override = get_effective_role(user, organization_id)

        if level is None or level < min_level:
            await _audit_deny(user, organization_id, min_level, level, db)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Requires {min_level.name} role or higher in this "
                    "organization"
                ),
            )

        if is_override:
            await _audit_instance_override(
                user, organization_id, min_level, db
            )

        return AuthContext(
            user=user,
            organization_id=organization_id,
            role_level=level,
            is_instance_override=is_override,
        )

    return dep


# Convenience aliases for the common min-level cases.
require_viewer = require_role(RoleLevel.VIEWER)
require_member = require_role(RoleLevel.MEMBER)
require_admin = require_role(RoleLevel.ADMIN)
require_owner = require_role(RoleLevel.OWNER)


# ---------------------------------------------------------------------------
# Cross-org guard
# ---------------------------------------------------------------------------


def assert_resource_in_org(
    resource_org_id: UUID,
    context_org_id: UUID,
    resource_name: str = "resource",
) -> None:
    """Cross-org leak guard. Call AFTER loading a resource by id.

    Returns **404** (not 403) on mismatch so callers can't enumerate
    resource IDs from other orgs. Matches the existing pattern in
    ``tool_bindings.py::_assert_context_in_org_or_404``.

    Example::

        composition = await db.get(Composition, composition_id)
        if composition is None:
            raise HTTPException(404)
        assert_resource_in_org(
            composition.organization_id,
            auth.organization_id,
            "composition",
        )
    """
    if resource_org_id != context_org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_name} not found",
        )
