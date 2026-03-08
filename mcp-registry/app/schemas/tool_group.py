"""
Pydantic schemas for ToolGroup API.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from ..models.tool_group import ToolGroupVisibility, ToolGroupItemType


class ToolGroupItemCreate(BaseModel):
    """Schema for adding an item to a tool group."""

    item_type: ToolGroupItemType = Field(
        default=ToolGroupItemType.TOOL,
        description="Type of item: tool or composition"
    )
    tool_id: Optional[UUID] = Field(
        None,
        description="Tool UUID (required if item_type=TOOL)"
    )
    composition_id: Optional[UUID] = Field(
        None,
        description="Composition UUID (required if item_type=COMPOSITION)"
    )
    order: int = Field(
        default=0,
        description="Display order within the group"
    )
    config: dict = Field(
        default_factory=dict,
        description="Optional configuration overrides"
    )


class ToolGroupItemResponse(BaseModel):
    """Schema for tool group item response."""

    id: UUID
    tool_group_id: UUID
    item_type: str
    tool_id: Optional[UUID]
    composition_id: Optional[UUID]
    order: int
    config: dict
    # Populated tool info when fetched
    tool_name: Optional[str] = None
    tool_description: Optional[str] = None
    server_id: Optional[UUID] = None
    server_name: Optional[str] = None

    class Config:
        from_attributes = True


class ToolGroupCreate(BaseModel):
    """Schema for creating a tool group."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the tool group"
    )
    description: Optional[str] = Field(
        None,
        description="Description of what this tool group is for"
    )
    icon: Optional[str] = Field(
        None,
        max_length=50,
        description="Icon name or emoji for UI display"
    )
    color: Optional[str] = Field(
        None,
        max_length=7,
        description="Hex color code for UI display (e.g., '#FF5733')"
    )
    visibility: ToolGroupVisibility = Field(
        default=ToolGroupVisibility.PRIVATE,
        description="Who can see and use this tool group"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Read-Only Agent",
                "description": "Tools that only read data, no write operations",
                "icon": "eye",
                "color": "#3B82F6",
                "visibility": "private"
            }
        }


class ToolGroupUpdate(BaseModel):
    """Schema for updating a tool group."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255
    )
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    visibility: Optional[ToolGroupVisibility] = None
    is_active: Optional[bool] = None


class ToolGroupResponse(BaseModel):
    """Schema for tool group response."""

    id: UUID
    user_id: UUID
    organization_id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    visibility: str
    is_active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    items: List[ToolGroupItemResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "organization_id": "123e4567-e89b-12d3-a456-426614174002",
                "name": "Read-Only Agent",
                "description": "Tools that only read data",
                "icon": "eye",
                "color": "#3B82F6",
                "visibility": "private",
                "is_active": True,
                "usage_count": 42,
                "last_used_at": "2024-01-15T10:30:00Z",
                "items": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class ToolGroupListResponse(BaseModel):
    """Schema for list of tool groups."""

    groups: List[ToolGroupResponse]
    total: int


class ToolInfoResponse(BaseModel):
    """Schema for available tool info (for selection UI)."""

    id: UUID
    server_id: UUID
    server_name: str
    tool_name: str
    display_name: Optional[str]
    description: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    # Whether this tool is already in a group
    in_groups: List[UUID] = []

    class Config:
        from_attributes = True
