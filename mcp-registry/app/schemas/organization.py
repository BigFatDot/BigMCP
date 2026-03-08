"""
Pydantic schemas for organization and team management.

Defines request/response models for organization and member endpoints.
"""

from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


# ===== Enums =====

class UserRoleEnum(str, Enum):
    """User role within an organization."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class OrganizationTypeEnum(str, Enum):
    """Type of organization."""
    PERSONAL = "personal"
    TEAM = "team"
    ENTERPRISE = "enterprise"


# ===== Organization Schemas =====

class OrganizationBase(BaseModel):
    """Base organization fields."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)


class OrganizationCreate(OrganizationBase):
    """Create organization request."""
    organization_type: OrganizationTypeEnum = OrganizationTypeEnum.TEAM


class OrganizationUpdate(BaseModel):
    """Update organization request."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    settings: Optional[dict] = None


class OrganizationResponse(BaseModel):
    """Organization response."""
    id: UUID
    name: str
    slug: str
    organization_type: OrganizationTypeEnum
    plan: str
    settings: dict
    max_contexts: int
    max_tool_bindings: int
    max_api_keys: int
    max_mcp_servers: int
    created_at: datetime
    updated_at: datetime
    member_count: Optional[int] = None

    class Config:
        from_attributes = True


class OrganizationListResponse(BaseModel):
    """List of organizations response."""
    organizations: List[OrganizationResponse]
    total: int


# ===== Member Schemas =====

class MemberBase(BaseModel):
    """Base member fields."""
    role: UserRoleEnum = UserRoleEnum.MEMBER


class MemberResponse(BaseModel):
    """Organization member response."""
    id: UUID
    user_id: UUID
    organization_id: UUID
    role: UserRoleEnum
    invited_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    # User info (joined)
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    user_avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class MemberListResponse(BaseModel):
    """List of members response."""
    members: List[MemberResponse]
    total: int


class MemberRoleUpdate(BaseModel):
    """Update member role request."""
    role: UserRoleEnum


class MemberRemoveResponse(BaseModel):
    """Member removal response."""
    success: bool
    message: str


# ===== Invitation Schemas =====

class InvitationCreate(BaseModel):
    """Create invitation request."""
    email: EmailStr
    role: UserRoleEnum = UserRoleEnum.MEMBER
    message: Optional[str] = Field(None, max_length=500)


class InvitationResponse(BaseModel):
    """Invitation response."""
    id: UUID
    organization_id: UUID
    email: str
    role: UserRoleEnum
    token: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime
    # Organization info (for display)
    organization_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvitationAccept(BaseModel):
    """Accept invitation request."""
    token: str


class InvitationRegister(BaseModel):
    """Register new user and accept invitation in one step."""
    name: Optional[str] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class InvitationRegisterResponse(BaseModel):
    """Response for invitation register (account creation + invitation acceptance)."""
    success: bool
    message: str
    user: dict  # UserResponse-like structure
    organization: dict  # OrganizationResponse-like structure
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class InvitationAcceptResponse(BaseModel):
    """Invitation acceptance response."""
    success: bool
    message: str
    organization: Optional[OrganizationResponse] = None


class PendingInvitationResponse(BaseModel):
    """Pending invitation info (for invited user)."""
    id: UUID
    organization_name: str
    organization_slug: str
    role: UserRoleEnum
    invited_by_name: Optional[str] = None
    expires_at: datetime

    class Config:
        from_attributes = True


# ===== Organization Stats =====

class OrganizationStats(BaseModel):
    """Organization usage statistics."""
    member_count: int
    mcp_server_count: int
    context_count: int
    api_key_count: int
    credential_count: int
    # Limits
    max_contexts: int
    max_tool_bindings: int
    max_api_keys: int
    max_mcp_servers: int
