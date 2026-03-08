"""
Permission Service - Composition execution permissions.

Checks if users have permission to execute compositions based on:
- User role in organization
- Composition allowed_roles configuration
- General RBAC rules
"""

import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.organization import OrganizationMember, UserRole
from ..orchestration.composition_store import CompositionInfo

logger = logging.getLogger(__name__)


class PermissionService:
    """
    Service for checking composition execution permissions.

    Implements IAM Delegation permission checks:
    - Role-based access control
    - Composition-specific allowed_roles
    - Default rules (e.g., VIEWERs cannot execute)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize permission service.

        Args:
            db: Async database session
        """
        self.db = db

    async def can_execute_composition(
        self,
        user_id: UUID,
        organization_id: UUID,
        composition: CompositionInfo
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user has permission to execute a composition.

        Args:
            user_id: User attempting to execute
            organization_id: Organization context
            composition: Composition to execute

        Returns:
            Tuple of (can_execute: bool, reason: Optional[str])
            - can_execute: True if user can execute, False otherwise
            - reason: Human-readable explanation if denied

        Example:
            can_execute, reason = await permission_service.can_execute_composition(
                user_id=user.id,
                organization_id=org.id,
                composition=composition
            )

            if not can_execute:
                raise HTTPException(status_code=403, detail=reason)
        """
        # Get user's role in organization
        user_role = await self._get_user_role(user_id, organization_id)

        if not user_role:
            return (False, "User is not a member of this organization")

        # Check composition-specific allowed_roles
        if composition.allowed_roles:
            # Convert role enum to string for comparison
            role_str = user_role.value if isinstance(user_role, UserRole) else str(user_role)

            if role_str not in composition.allowed_roles:
                allowed_str = ", ".join(composition.allowed_roles)
                return (
                    False,
                    f"Insufficient permissions. Required role: {allowed_str}, your role: {role_str}"
                )

        # Default rule: VIEWERs cannot execute (read-only)
        if user_role == UserRole.VIEWER:
            # Exception: If composition explicitly allows viewers
            if "viewer" not in [r.lower() for r in composition.allowed_roles]:
                return (False, "Viewers have read-only access and cannot execute compositions")

        # All checks passed
        return (True, None)

    async def can_view_composition(
        self,
        user_id: UUID,
        organization_id: UUID,
        composition: CompositionInfo
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can view/read a composition (less restrictive than execute).

        Args:
            user_id: User attempting to view
            organization_id: Organization context
            composition: Composition to view

        Returns:
            Tuple of (can_view: bool, reason: Optional[str])
        """
        # Get user's role in organization
        user_role = await self._get_user_role(user_id, organization_id)

        if not user_role:
            return (False, "User is not a member of this organization")

        # All organization members can view compositions by default
        return (True, None)

    async def can_edit_composition(
        self,
        user_id: UUID,
        organization_id: UUID,
        composition: CompositionInfo
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can edit/modify a composition.

        Args:
            user_id: User attempting to edit
            organization_id: Organization context
            composition: Composition to edit

        Returns:
            Tuple of (can_edit: bool, reason: Optional[str])
        """
        # Get user's role in organization
        user_role = await self._get_user_role(user_id, organization_id)

        if not user_role:
            return (False, "User is not a member of this organization")

        # Only OWNER, ADMIN, and MEMBER can edit
        if user_role in [UserRole.OWNER, UserRole.ADMIN, UserRole.MEMBER]:
            return (True, None)

        return (False, f"Role '{user_role.value}' cannot edit compositions")

    async def _get_user_role(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> Optional[UserRole]:
        """
        Get user's role in an organization.

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            UserRole enum, or None if user is not a member
        """
        query = select(OrganizationMember).where(
            and_(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == organization_id
            )
        )

        result = await self.db.execute(query)
        member = result.scalar_one_or_none()

        if not member:
            return None

        return member.role

    async def get_user_role_str(
        self,
        user_id: UUID,
        organization_id: UUID
    ) -> Optional[str]:
        """
        Get user's role as string (for logging/audit).

        Args:
            user_id: User UUID
            organization_id: Organization UUID

        Returns:
            Role as string ("owner", "admin", "member", "viewer"), or None
        """
        role = await self._get_user_role(user_id, organization_id)
        if role is None:
            return None

        return role.value


# Convenience function for dependency injection
def get_permission_service(db: AsyncSession) -> PermissionService:
    """
    Get or create permission service instance.

    Args:
        db: Async database session

    Returns:
        PermissionService instance

    Usage:
        from app.services.permission_service import get_permission_service

        permission_service = get_permission_service(db)
        can_execute, reason = await permission_service.can_execute_composition(...)
    """
    return PermissionService(db)
