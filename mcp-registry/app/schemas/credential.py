"""
Pydantic schemas for Credential API.

Handles both user-level and organization-level credentials.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# ==================== User Credential Schemas ====================

class UserCredentialCreate(BaseModel):
    """Schema for creating user credentials."""

    server_id: UUID = Field(
        ...,
        description="MCP server UUID to configure credentials for"
    )
    credentials: Dict[str, Any] = Field(
        ...,
        description="Environment variables as key-value pairs (e.g., {'API_KEY': 'secret'})"
    )
    name: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional name for this credential set (e.g., 'My Personal OpenAI Key')"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "123e4567-e89b-12d3-a456-426614174000",
                "credentials": {
                    "OPENAI_API_KEY": "sk-..."
                },
                "name": "My Personal OpenAI Key",
                "description": "My own OpenAI API key for personal projects"
            }
        }


class UserCredentialUpdate(BaseModel):
    """Schema for updating user credentials."""

    credentials: Optional[Dict[str, Any]] = Field(
        None,
        description="New credentials (replaces existing)"
    )
    name: Optional[str] = Field(
        None,
        max_length=255,
        description="New name"
    )
    description: Optional[str] = Field(
        None,
        description="New description"
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether credentials are active"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "credentials": {
                    "OPENAI_API_KEY": "sk-new-key..."
                },
                "name": "Updated Personal Key"
            }
        }


class UserCredentialResponse(BaseModel):
    """Schema for user credential response (credentials are NEVER returned)."""

    id: UUID
    user_id: UUID
    server_id: UUID
    organization_id: UUID

    name: Optional[str]
    description: Optional[str]
    is_active: bool

    last_used_at: Optional[datetime]
    is_validated: bool
    validated_at: Optional[datetime]

    created_at: datetime
    updated_at: datetime

    # Masked credentials for display (optional)
    credentials_masked: Optional[Dict[str, str]] = Field(
        None,
        description="Masked credentials (e.g., {'API_KEY': 'sk-***123'})"
    )

    # Server status info (populated from mcp_servers table)
    server_status: Optional[str] = Field(
        None,
        description="Server process status: running, stopped, error, etc."
    )
    server_enabled: Optional[bool] = Field(
        None,
        description="Whether server is enabled"
    )
    is_visible_to_oauth_clients: Optional[bool] = Field(
        None,
        description="Whether server is visible to OAuth clients (web dashboard). Hidden servers are still accessible via API keys."
    )

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "server_id": "123e4567-e89b-12d3-a456-426614174002",
                "organization_id": "123e4567-e89b-12d3-a456-426614174003",
                "name": "My Personal OpenAI Key",
                "description": "My own OpenAI API key",
                "is_active": True,
                "last_used_at": "2024-01-15T10:30:00Z",
                "is_validated": True,
                "validated_at": "2024-01-10T14:20:00Z",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-10T14:20:00Z",
                "credentials_masked": {
                    "OPENAI_API_KEY": "sk-***xyz"
                }
            }
        }


# ==================== Organization Credential Schemas ====================

class OrganizationCredentialCreate(BaseModel):
    """Schema for creating organization credentials (admin only)."""

    server_id: Optional[UUID] = Field(
        None,
        description="MCP server UUID to configure credentials for (if server already exists)"
    )
    marketplace_server_id: Optional[str] = Field(
        None,
        description="Marketplace server ID to auto-create and configure (e.g., 'grist-mcp')"
    )
    credentials: Dict[str, Any] = Field(
        ...,
        description="Environment variables as key-value pairs"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name for this credential set (required)"
    )
    description: Optional[str] = Field(
        None,
        description="Description (e.g., 'Company OpenAI account for all employees')"
    )
    visible_to_users: bool = Field(
        False,
        description="If True, users can see that org credentials exist (but not values)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "123e4567-e89b-12d3-a456-426614174000",
                "credentials": {
                    "OPENAI_API_KEY": "sk-org..."
                },
                "name": "Company OpenAI Account",
                "description": "Shared OpenAI account for all employees",
                "visible_to_users": True
            }
        }


class OrganizationCredentialUpdate(BaseModel):
    """Schema for updating organization credentials (admin only)."""

    credentials: Optional[Dict[str, Any]] = Field(
        None,
        description="New credentials (replaces existing)"
    )
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New name"
    )
    description: Optional[str] = Field(
        None,
        description="New description"
    )
    visible_to_users: Optional[bool] = Field(
        None,
        description="New visibility setting"
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether credentials are active"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Company Account",
                "visible_to_users": False
            }
        }


class OrganizationCredentialResponse(BaseModel):
    """Schema for organization credential response (credentials are NEVER returned to regular users)."""

    id: UUID
    organization_id: UUID
    server_id: UUID

    name: str
    description: Optional[str]
    is_active: bool

    visible_to_users: bool
    usage_count: int
    last_used_at: Optional[datetime]

    created_by: Optional[UUID]
    updated_by: Optional[UUID]

    created_at: datetime
    updated_at: datetime

    # Masked credentials for admin display only (optional)
    credentials_masked: Optional[Dict[str, str]] = Field(
        None,
        description="Masked credentials (admins only)"
    )

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "organization_id": "123e4567-e89b-12d3-a456-426614174001",
                "server_id": "123e4567-e89b-12d3-a456-426614174002",
                "name": "Company OpenAI Account",
                "description": "Shared account for all employees",
                "is_active": True,
                "visible_to_users": True,
                "usage_count": 1523,
                "last_used_at": "2024-01-15T10:30:00Z",
                "created_by": "123e4567-e89b-12d3-a456-426614174003",
                "updated_by": "123e4567-e89b-12d3-a456-426614174003",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-10T14:20:00Z",
                "credentials_masked": {
                    "OPENAI_API_KEY": "sk-***xyz"
                }
            }
        }


# ==================== Resolution Schemas ====================

class CredentialResolutionResponse(BaseModel):
    """Schema for resolved credentials (for internal use only)."""

    server_id: UUID
    source: str = Field(
        ...,
        description="Source of credentials: 'user' or 'organization'"
    )
    credentials_masked: Dict[str, str] = Field(
        ...,
        description="Masked credentials for display"
    )
    last_used_at: Optional[datetime]

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": "123e4567-e89b-12d3-a456-426614174000",
                "source": "user",
                "credentials_masked": {
                    "OPENAI_API_KEY": "sk-***xyz"
                },
                "last_used_at": "2024-01-15T10:30:00Z"
            }
        }
