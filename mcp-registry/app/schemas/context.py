"""
Pydantic schemas for Context API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ContextCreate(BaseModel):
    """Schema for creating a context."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable name"
    )
    context_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Type: workspace, project, folder, task, document, etc."
    )
    parent_id: Optional[UUID] = Field(
        None,
        description="Parent context UUID (null for root)"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description"
    )
    ttl_seconds: Optional[int] = Field(
        None,
        ge=0,
        description="Time-to-live in seconds (null = permanent)"
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible metadata storage"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Project X",
                "context_type": "project",
                "parent_id": None,
                "description": "Main project workspace",
                "ttl_seconds": None,
                "metadata": {
                    "team": "alpha",
                    "priority": "high"
                }
            }
        }


class ContextUpdate(BaseModel):
    """Schema for updating a context."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New name (will update path)"
    )
    description: Optional[str] = Field(
        None,
        description="New description"
    )
    meta: Optional[Dict[str, Any]] = Field(
        None,
        description="New metadata (replaces existing)"
    )
    ttl_seconds: Optional[int] = Field(
        None,
        ge=0,
        description="New TTL in seconds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Updated description",
                "metadata": {
                    "priority": "medium"
                }
            }
        }


class ContextResponse(BaseModel):
    """Schema for context response."""

    id: UUID
    organization_id: UUID
    path: str
    name: str
    description: Optional[str]
    context_type: str
    parent_id: Optional[UUID]
    depth: int

    ttl_seconds: Optional[int]
    expires_at: Optional[datetime]
    is_expired: bool
    archived: bool

    meta: Dict[str, Any]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "organization_id": "123e4567-e89b-12d3-a456-426614174001",
                "path": "root.team_alpha.project_x",
                "name": "Project X",
                "description": "Main project workspace",
                "context_type": "project",
                "parent_id": "123e4567-e89b-12d3-a456-426614174002",
                "depth": 3,
                "ttl_seconds": None,
                "expires_at": None,
                "is_expired": False,
                "archived": False,
                "metadata": {
                    "team": "alpha",
                    "priority": "high"
                },
                "created_by": "123e4567-e89b-12d3-a456-426614174003",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class ContextTreeNode(BaseModel):
    """Schema for a node in context tree."""

    context: ContextResponse
    children: List['ContextTreeNode'] = Field(default_factory=list)

    class Config:
        from_attributes = True


# Enable forward references for recursive model
ContextTreeNode.model_rebuild()


class ContextTreeResponse(BaseModel):
    """Schema for context tree response."""

    root: ContextTreeNode
    total_nodes: int

    class Config:
        json_schema_extra = {
            "example": {
                "root": {
                    "context": {
                        "id": "...",
                        "path": "root.team_alpha",
                        "name": "Team Alpha",
                        "context_type": "workspace"
                    },
                    "children": [
                        {
                            "context": {
                                "id": "...",
                                "path": "root.team_alpha.project_x",
                                "name": "Project X",
                                "context_type": "project"
                            },
                            "children": []
                        }
                    ]
                },
                "total_nodes": 2
            }
        }
