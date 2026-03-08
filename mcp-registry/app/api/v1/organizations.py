"""
Organization and Team Management API.

Endpoints for managing organizations, members, and invitations.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.database import get_async_session
from ...models.organization import Organization, OrganizationMember, UserRole
from ...models.user import User
from ...models.invitation import Invitation, InvitationStatus
from ...models.api_key import APIKey
from ...schemas.organization import (
    OrganizationResponse,
    OrganizationUpdate,
    OrganizationListResponse,
    MemberResponse,
    MemberListResponse,
    MemberRoleUpdate,
    MemberRemoveResponse,
    InvitationCreate,
    InvitationResponse,
    InvitationAccept,
    InvitationAcceptResponse,
    InvitationRegister,
    InvitationRegisterResponse,
    PendingInvitationResponse,
    OrganizationStats,
    UserRoleEnum,
)
from ..dependencies import get_current_user, get_current_user_jwt
from ...core.edition import is_community, is_saas, is_enterprise

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


# ===== Helper Functions =====

async def get_user_membership(
    db: AsyncSession,
    user_id: UUID,
    organization_id: UUID
) -> Optional[OrganizationMember]:
    """Get user's membership in an organization."""
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user_id)
        .where(OrganizationMember.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def require_org_admin(
    db: AsyncSession,
    user_id: UUID,
    organization_id: UUID
) -> OrganizationMember:
    """Require user to be admin or owner of organization."""
    membership = await get_user_membership(db, user_id, organization_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )
    if membership.role not in [UserRole.ADMIN, UserRole.OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role required"
        )
    return membership


async def require_org_owner(
    db: AsyncSession,
    user_id: UUID,
    organization_id: UUID
) -> OrganizationMember:
    """Require user to be owner of organization."""
    membership = await get_user_membership(db, user_id, organization_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )
    if membership.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner role required"
        )
    return membership


async def count_organization_members(
    db: AsyncSession,
    organization_id: UUID
) -> int:
    """
    Count active members in an organization.

    Used for billing sync when updating LemonSqueezy subscription quantity.

    Args:
        db: Database session
        organization_id: Organization ID

    Returns:
        Number of active members
    """
    result = await db.execute(
        select(func.count()).select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
    )
    return result.scalar() or 0


def membership_to_response(membership: OrganizationMember) -> MemberResponse:
    """Convert OrganizationMember to MemberResponse."""
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        role=UserRoleEnum(membership.role.value),
        invited_by=membership.invited_by,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
        user_email=membership.user.email if membership.user else None,
        user_name=membership.user.name if membership.user else None,
        user_avatar_url=membership.user.avatar_url if membership.user else None,
    )


# ===== Organization Endpoints =====

@router.get("/", response_model=OrganizationListResponse)
async def list_organizations(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all organizations the current user is a member of.
    """
    user, _ = auth

    # Get organizations with member count
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .options(selectinload(Organization.members))
    )
    organizations = result.scalars().all()

    org_responses = []
    for org in organizations:
        org_responses.append(OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            organization_type=org.organization_type.value,
            plan=org.plan,
            settings=org.settings or {},
            max_contexts=org.max_contexts,
            max_tool_bindings=org.max_tool_bindings,
            max_api_keys=org.max_api_keys,
            max_mcp_servers=org.max_mcp_servers,
            created_at=org.created_at,
            updated_at=org.updated_at,
            member_count=len(org.members)
        ))

    return OrganizationListResponse(
        organizations=org_responses,
        total=len(org_responses)
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get organization details.

    Requires membership in the organization.
    """
    user, _ = auth

    # Check membership
    membership = await get_user_membership(db, user.id, organization_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )

    # Get organization with members
    result = await db.execute(
        select(Organization)
        .where(Organization.id == organization_id)
        .options(selectinload(Organization.members))
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        organization_type=org.organization_type.value,
        plan=org.plan,
        settings=org.settings or {},
        max_contexts=org.max_contexts,
        max_tool_bindings=org.max_tool_bindings,
        max_api_keys=org.max_api_keys,
        max_mcp_servers=org.max_mcp_servers,
        created_at=org.created_at,
        updated_at=org.updated_at,
        member_count=len(org.members)
    )


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: UUID,
    update: OrganizationUpdate,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update organization settings.

    Requires Admin or Owner role.
    """
    user, _ = auth

    # Check admin permission
    await require_org_admin(db, user.id, organization_id)

    # Get organization
    result = await db.execute(
        select(Organization)
        .where(Organization.id == organization_id)
        .options(selectinload(Organization.members))
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Update fields
    if update.name is not None:
        org.name = update.name
    if update.settings is not None:
        org.settings = update.settings

    # Store member count before commit (members already loaded)
    member_count = len(org.members)

    await db.commit()
    await db.refresh(org)

    logger.info(f"Organization {organization_id} updated by user {user.id}")

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        organization_type=org.organization_type.value,
        plan=org.plan,
        settings=org.settings or {},
        max_contexts=org.max_contexts,
        max_tool_bindings=org.max_tool_bindings,
        max_api_keys=org.max_api_keys,
        max_mcp_servers=org.max_mcp_servers,
        created_at=org.created_at,
        updated_at=org.updated_at,
        member_count=member_count
    )


@router.get("/{organization_id}/stats", response_model=OrganizationStats)
async def get_organization_stats(
    organization_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get organization usage statistics.

    Requires membership in the organization.
    """
    user, _ = auth

    # Check membership
    membership = await get_user_membership(db, user.id, organization_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )

    # Get organization
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Count resources
    from ...models.mcp_server import MCPServer
    from ...models.context import Context
    from ...models.api_key import APIKey
    from ...models.user_credential import OrganizationCredential

    member_count = await db.scalar(
        select(func.count()).select_from(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
    )
    server_count = await db.scalar(
        select(func.count()).select_from(MCPServer)
        .where(MCPServer.organization_id == organization_id)
    )
    context_count = await db.scalar(
        select(func.count()).select_from(Context)
        .where(Context.organization_id == organization_id)
    )
    api_key_count = await db.scalar(
        select(func.count()).select_from(APIKey)
        .where(APIKey.organization_id == organization_id)
    )
    credential_count = await db.scalar(
        select(func.count()).select_from(OrganizationCredential)
        .where(OrganizationCredential.organization_id == organization_id)
    )

    return OrganizationStats(
        member_count=member_count or 0,
        mcp_server_count=server_count or 0,
        context_count=context_count or 0,
        api_key_count=api_key_count or 0,
        credential_count=credential_count or 0,
        max_contexts=org.max_contexts,
        max_tool_bindings=org.max_tool_bindings,
        max_api_keys=org.max_api_keys,
        max_mcp_servers=org.max_mcp_servers,
    )


# ===== Member Endpoints =====

@router.get("/{organization_id}/members", response_model=MemberListResponse)
async def list_members(
    organization_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all members of an organization.

    Requires membership in the organization.
    """
    user, _ = auth

    # Check membership
    membership = await get_user_membership(db, user.id, organization_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )

    # Get all members with user info
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .options(selectinload(OrganizationMember.user))
        .order_by(OrganizationMember.created_at)
    )
    members = result.scalars().all()

    member_responses = [membership_to_response(m) for m in members]

    return MemberListResponse(
        members=member_responses,
        total=len(member_responses)
    )


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    organization_id: UUID,
    user_id: UUID,
    update: MemberRoleUpdate,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a member's role.

    Requires Admin or Owner role.
    Cannot change the owner's role (transfer ownership separately).
    """
    current_user, _ = auth

    # Check admin permission
    current_membership = await require_org_admin(db, current_user.id, organization_id)

    # Get target member
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.user_id == user_id)
        .options(selectinload(OrganizationMember.user))
    )
    target_membership = result.scalar_one_or_none()

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Cannot change owner's role
    if target_membership.role == UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change owner's role. Transfer ownership instead."
        )

    # Only owner can promote to admin
    if update.role == UserRoleEnum.ADMIN and current_membership.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can promote members to admin"
        )

    # Cannot set role to owner through this endpoint
    if update.role == UserRoleEnum.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use transfer ownership endpoint to change owner"
        )

    # Update role
    target_membership.role = UserRole(update.role.value)
    await db.commit()
    await db.refresh(target_membership)

    logger.info(f"Member {user_id} role changed to {update.role} in org {organization_id}")

    return membership_to_response(target_membership)


@router.delete("/{organization_id}/members/{user_id}", response_model=MemberRemoveResponse)
async def remove_member(
    organization_id: UUID,
    user_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Remove a member from the organization.

    Requires Admin or Owner role.
    Cannot remove the owner.
    Members can remove themselves (leave organization).
    """
    current_user, _ = auth

    # Get current user's membership
    current_membership = await get_user_membership(db, current_user.id, organization_id)
    if not current_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization"
        )

    # Get target member
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .where(OrganizationMember.user_id == user_id)
    )
    target_membership = result.scalar_one_or_none()

    if not target_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Cannot remove owner
    if target_membership.role == UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove organization owner"
        )

    # Check permissions: admin/owner can remove anyone, member can only remove self
    is_self = current_user.id == user_id
    is_admin = current_membership.role in [UserRole.ADMIN, UserRole.OWNER]

    if not is_self and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Owner role required to remove other members"
        )

    # Remove member
    await db.delete(target_membership)
    await db.commit()

    # SaaS Team billing sync: Decrement quantity AFTER removing member
    if is_saas():
        from ..v1.subscriptions import get_organization_subscription, update_subscription_quantity
        from ...models.subscription import SubscriptionTier

        subscription = await get_organization_subscription(db, organization_id)

        if subscription and subscription.tier == SubscriptionTier.TEAM:
            # Count remaining members AFTER removal
            remaining_count = await count_organization_members(db, organization_id)

            # Update LemonSqueezy subscription quantity
            # invoice_immediately=False → credit applied at next billing cycle
            await update_subscription_quantity(
                subscription.lemonsqueezy_subscription_id,
                remaining_count,
                invoice_immediately=False
            )

            logger.info(f"💳 Decremented billing to {remaining_count} seats for org {organization_id}")

    action = "left" if is_self else "removed from"
    logger.info(f"User {user_id} {action} organization {organization_id}")

    return MemberRemoveResponse(
        success=True,
        message=f"Member {'left' if is_self else 'removed from'} organization"
    )


# ===== Invitation Endpoints =====

@router.post("/{organization_id}/invitations", response_model=InvitationResponse)
async def create_invitation(
    organization_id: UUID,
    invitation: InvitationCreate,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Invite a user to join the organization.

    Requires Admin or Owner role.
    Creates a pending invitation with a unique token.
    """
    user, _ = auth

    # Edition validation: Community edition doesn't support team features
    if is_community():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team features are not available in Community edition. "
                   "Upgrade to Enterprise for team collaboration with unlimited users."
        )

    # SaaS validation: Check subscription tier
    if is_saas():
        from ..v1.subscriptions import get_organization_subscription
        from ...models.subscription import SubscriptionTier

        subscription = await get_organization_subscription(db, organization_id)

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No active subscription found. Please subscribe to continue."
            )

        if not subscription.is_active:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Subscription {subscription.status.value}. Please renew to invite members."
            )

        if subscription.tier == SubscriptionTier.INDIVIDUAL:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Individual plan is limited to 1 user. "
                       "Upgrade to Team (€4.99/month + €4.99/user/month) for unlimited team members."
            )

    # Check admin permission
    await require_org_admin(db, user.id, organization_id)

    # Check if user is already a member
    email_lower = invitation.email.lower()
    existing_user = await db.execute(
        select(User).where(User.email == email_lower)
    )
    existing_user = existing_user.scalar_one_or_none()

    if existing_user:
        existing_membership = await get_user_membership(db, existing_user.id, organization_id)
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this organization"
            )

    # Check for existing pending invitation
    existing_invitation = await db.execute(
        select(Invitation)
        .where(Invitation.organization_id == organization_id)
        .where(Invitation.email == email_lower)
        .where(Invitation.status == InvitationStatus.PENDING)
    )
    existing_invitation = existing_invitation.scalar_one_or_none()

    if existing_invitation and existing_invitation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending invitation already exists for this email"
        )

    # Get organization name for response
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    # Create invitation
    new_invitation = Invitation.create_invitation(
        organization_id=organization_id,
        invited_by=user.id,
        email=email_lower,
        role=invitation.role.value,
        message=invitation.message,
        expires_in_days=7
    )

    db.add(new_invitation)
    await db.commit()
    await db.refresh(new_invitation)

    logger.info(f"Invitation created for {email_lower} to org {organization_id}")

    # Send invitation email
    from ...services.email_service import get_email_service
    from ...core.config import settings

    email_service = get_email_service()
    if email_service.is_configured:
        domain = settings.domain or "http://localhost:3000"
        invitation_link = f"{domain}/invitations/{new_invitation.token}/accept"

        result = email_service.send_invitation_email(
            to_email=email_lower,
            invitation_link=invitation_link,
            organization_name=org.name,
            inviter_name=user.name,
            role=invitation.role.value,
            message=invitation.message,
            expires_days=settings.INVITATION_EXPIRE_DAYS
        )

        if result.success:
            logger.info(f"Invitation email sent to {email_lower}")
        else:
            logger.warning(f"Failed to send invitation email to {email_lower}: {result.error}")
    else:
        logger.warning(f"SMTP not configured, invitation token for {email_lower}: {new_invitation.token}")

    return InvitationResponse(
        id=new_invitation.id,
        organization_id=new_invitation.organization_id,
        email=new_invitation.email,
        role=UserRoleEnum(new_invitation.role),
        token=new_invitation.token,
        invited_by=new_invitation.invited_by,
        expires_at=new_invitation.expires_at,
        created_at=new_invitation.created_at,
        organization_name=org.name
    )


@router.get("/{organization_id}/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    organization_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    List all invitations for an organization.

    Requires Admin or Owner role.
    """
    user, _ = auth

    # Check admin permission
    await require_org_admin(db, user.id, organization_id)

    # Build query
    query = (
        select(Invitation)
        .where(Invitation.organization_id == organization_id)
        .order_by(Invitation.created_at.desc())
    )

    if status_filter:
        try:
            status_enum = InvitationStatus(status_filter)
            query = query.where(Invitation.status == status_enum)
        except ValueError:
            pass

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Get organization name
    org_result = await db.execute(
        select(Organization.name).where(Organization.id == organization_id)
    )
    org_name = org_result.scalar_one_or_none()

    return [
        InvitationResponse(
            id=inv.id,
            organization_id=inv.organization_id,
            email=inv.email,
            role=UserRoleEnum(inv.role),
            token=inv.token,
            invited_by=inv.invited_by,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            organization_name=org_name
        )
        for inv in invitations
    ]


@router.delete("/{organization_id}/invitations/{invitation_id}")
async def revoke_invitation(
    organization_id: UUID,
    invitation_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Revoke a pending invitation.

    Requires Admin or Owner role.
    """
    user, _ = auth

    # Check admin permission
    await require_org_admin(db, user.id, organization_id)

    # Get invitation
    result = await db.execute(
        select(Invitation)
        .where(Invitation.id == invitation_id)
        .where(Invitation.organization_id == organization_id)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot revoke invitation with status: {invitation.status.value}"
        )

    # Revoke invitation
    invitation.status = InvitationStatus.REVOKED
    await db.commit()

    logger.info(f"Invitation {invitation_id} revoked")

    return {"success": True, "message": "Invitation revoked"}


# ===== Invitation Accept Endpoints (for invited users) =====

@router.get("/invitations/pending", response_model=list[PendingInvitationResponse])
async def get_my_pending_invitations(
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get pending invitations for the current user's email.
    """
    result = await db.execute(
        select(Invitation)
        .join(Organization)
        .join(User, Invitation.invited_by == User.id)
        .where(Invitation.email == user.email.lower())
        .where(Invitation.status == InvitationStatus.PENDING)
        .options(
            selectinload(Invitation.organization),
            selectinload(Invitation.inviter)
        )
    )
    invitations = result.scalars().all()

    return [
        PendingInvitationResponse(
            id=inv.id,
            organization_name=inv.organization.name,
            organization_slug=inv.organization.slug,
            role=UserRoleEnum(inv.role),
            invited_by_name=inv.inviter.name if inv.inviter else None,
            expires_at=inv.expires_at
        )
        for inv in invitations
        if inv.is_valid
    ]


@router.post("/invitations/{token}/accept", response_model=InvitationAcceptResponse)
async def accept_invitation(
    token: str,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Accept an invitation using its token.

    Creates a new membership for the current user.
    """
    # Find invitation by token
    result = await db.execute(
        select(Invitation)
        .where(Invitation.token == token)
        .options(selectinload(Invitation.organization))
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    # Validate invitation
    if not invitation.is_valid:
        if invitation.is_expired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invitation has expired"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invitation is not valid (status: {invitation.status.value})"
        )

    # Check email matches
    if invitation.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is for a different email address"
        )

    # Check if already a member
    existing_membership = await get_user_membership(db, user.id, invitation.organization_id)
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this organization"
        )

    # SaaS Team billing sync: Increment quantity BEFORE creating member
    if is_saas():
        from ..v1.subscriptions import get_organization_subscription, update_subscription_quantity
        from ...models.subscription import SubscriptionTier

        subscription = await get_organization_subscription(db, invitation.organization_id)

        if subscription and subscription.tier == SubscriptionTier.TEAM:
            # Count current members BEFORE adding new one
            current_count = await count_organization_members(db, invitation.organization_id)
            new_count = current_count + 1

            # Update LemonSqueezy subscription quantity
            success = await update_subscription_quantity(
                subscription.lemonsqueezy_subscription_id,
                new_count,
                invoice_immediately=True  # Charge prorata immediately
            )

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Billing service unavailable. Please try again later."
                )

            logger.info(f"💰 Incremented billing to {new_count} seats for org {invitation.organization_id}")

    # Create membership
    membership = OrganizationMember(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role=UserRole(invitation.role),
        invited_by=invitation.invited_by
    )
    db.add(membership)

    # Update invitation status
    from datetime import datetime, timezone
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_user_id = user.id

    await db.commit()

    logger.info(f"User {user.id} accepted invitation to org {invitation.organization_id}")

    org = invitation.organization
    return InvitationAcceptResponse(
        success=True,
        message=f"You are now a member of {org.name}",
        organization=OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            organization_type=org.organization_type.value,
            plan=org.plan,
            settings=org.settings or {},
            max_contexts=org.max_contexts,
            max_tool_bindings=org.max_tool_bindings,
            max_api_keys=org.max_api_keys,
            max_mcp_servers=org.max_mcp_servers,
            created_at=org.created_at,
            updated_at=org.updated_at,
        )
    )


@router.post("/invitations/{token}/decline")
async def decline_invitation(
    token: str,
    user: User = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Decline an invitation.
    """
    # Find invitation by token
    result = await db.execute(
        select(Invitation).where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is not pending"
        )

    # Check email matches (optional - could allow anyone to decline)
    if invitation.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation is for a different email address"
        )

    # Update status
    invitation.status = InvitationStatus.DECLINED
    await db.commit()

    logger.info(f"User {user.id} declined invitation {invitation.id}")

    return {"success": True, "message": "Invitation declined"}


@router.post("/invitations/{token}/register", response_model=InvitationRegisterResponse)
async def register_and_accept_invitation(
    token: str,
    data: InvitationRegister,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Register a new user account and accept invitation in one step.

    This endpoint is for invited users who don't have an account yet.
    It creates their account and automatically accepts the invitation.

    Returns:
        InvitationRegisterResponse: Created user info with tokens and organization
    """
    from datetime import datetime, timezone
    from ...models.user import User, AuthProvider
    from ...services.auth_service import AuthService
    from ...core.config import settings

    # Find invitation by token
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.organization))
        .where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is not pending"
        )

    # Check expiration
    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )

    # Check if user with this email already exists
    existing_user_result = await db.execute(
        select(User).where(User.email == invitation.email.lower())
    )
    existing_user = existing_user_result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please login and accept the invitation from your dashboard."
        )

    # Community edition: enforce user limit
    from ...core.edition import get_edition, Edition
    from sqlalchemy import func as sql_func

    edition = get_edition()
    if edition == Edition.COMMUNITY:
        user_count_result = await db.execute(select(sql_func.count(User.id)))
        user_count = user_count_result.scalar()

        if user_count >= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "user_limit_exceeded",
                    "message": "Community edition is limited to 1 user. Upgrade to Enterprise for unlimited users.",
                    "edition": "community",
                    "current_users": user_count,
                    "max_users": 1,
                    "upgrade_url": "https://bigmcp.cloud/pricing"
                }
            )

    # Create the user
    auth_service = AuthService(db)
    password_hash = AuthService.hash_password(data.password)

    user = User(
        email=invitation.email.lower(),
        name=data.name,
        auth_provider=AuthProvider.LOCAL,
        password_hash=password_hash,
        email_verified=True  # Email is verified since they received the invitation
    )
    db.add(user)
    await db.flush()

    # Create personal organization for user (they should have their own org too)
    org_name = f"{data.name}'s Organization" if data.name else f"{invitation.email}'s Organization"
    personal_org = Organization(
        name=org_name,
        slug=f"org-{user.id}",
        organization_type="personal"
    )
    db.add(personal_org)
    await db.flush()

    # Create membership in personal org (as admin)
    personal_membership = OrganizationMember(
        user_id=user.id,
        organization_id=personal_org.id,
        role=UserRole.ADMIN
    )
    db.add(personal_membership)

    # Accept the invitation - add to invited organization
    role_mapping = {
        "owner": UserRole.OWNER,
        "admin": UserRole.ADMIN,
        "member": UserRole.MEMBER,
        "viewer": UserRole.VIEWER,
    }
    invited_role = role_mapping.get(invitation.role, UserRole.MEMBER)

    team_membership = OrganizationMember(
        user_id=user.id,
        organization_id=invitation.organization_id,
        role=invited_role
    )
    db.add(team_membership)

    # Mark invitation as accepted
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)

    # Generate tokens (for the invited organization, not personal)
    access_token = auth_service.create_access_token(user.id, invitation.organization_id)
    refresh_token = auth_service.create_refresh_token(user.id)

    # Build response
    org = invitation.organization
    org_response = {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "organization_type": org.organization_type,
        "plan": org.plan,
    }

    user_response = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "auth_provider": user.auth_provider.value if hasattr(user.auth_provider, 'value') else str(user.auth_provider),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "email_verified": user.email_verified,
    }

    logger.info(f"User {user.id} registered via invitation {invitation.id} and joined organization {org.id}")

    return InvitationRegisterResponse(
        success=True,
        message=f"Account created and joined {org.name}",
        user=user_response,
        organization=org_response,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/invitations/{token}/info")
async def get_invitation_info(
    token: str,
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get public information about an invitation by token.

    This endpoint is public (no auth required) so users can see invitation
    details before deciding to register or login.

    Returns:
        Invitation info including organization name, role, and whether
        an account already exists for the invited email.
    """
    from datetime import datetime, timezone
    from ...models.user import User

    # Find invitation by token
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.organization))
        .options(selectinload(Invitation.inviter))
        .where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    # Check if expired
    is_expired = invitation.expires_at < datetime.now(timezone.utc)

    # Check if already used
    is_used = invitation.status != InvitationStatus.PENDING

    # Check if user already exists
    existing_user_result = await db.execute(
        select(User).where(User.email == invitation.email.lower())
    )
    existing_user = existing_user_result.scalar_one_or_none()
    user_exists = existing_user is not None

    return {
        "valid": not is_expired and not is_used,
        "expired": is_expired,
        "status": invitation.status,
        "email": invitation.email,
        "role": invitation.role,
        "organization": {
            "id": str(invitation.organization.id),
            "name": invitation.organization.name,
            "slug": invitation.organization.slug,
        },
        "inviter": {
            "name": invitation.inviter.name if invitation.inviter else None,
            "email": invitation.inviter.email if invitation.inviter else None,
        } if invitation.inviter else None,
        "user_exists": user_exists,
        "expires_at": invitation.expires_at.isoformat(),
        "message": "Please login and accept the invitation" if user_exists else "Create an account to join"
    }
