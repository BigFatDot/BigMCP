"""
Pydantic schemas for Tool API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Schema for tool response."""

    id: UUID
    server_id: UUID
    organization_id: UUID
    tool_name: str
    display_name: Optional[str]
    description: Optional[str]
    parameters_schema: Dict[str, Any]
    returns_schema: Optional[Dict[str, Any]]
    tags: Optional[List[str]]
    category: Optional[str]
    is_visible_to_oauth_clients: bool

    # Metadata
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "server_id": "123e4567-e89b-12d3-a456-426614174001",
                "organization_id": "123e4567-e89b-12d3-a456-426614174002",
                "tool_name": "create_document",
                "display_name": "Create Document",
                "description": "Create a new document in Grist",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["title"]
                },
                "tags": ["grist", "document"],
                "category": "database",
                "is_visible_to_oauth_clients": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class ToolUpdateVisibility(BaseModel):
    """Schema for updating tool visibility."""

    is_visible_to_oauth_clients: bool = Field(
        ...,
        description="Show/hide tool from OAuth clients (still available for API keys)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_visible_to_oauth_clients": False
            }
        }


class ToolListResponse(BaseModel):
    """Schema for list of tools."""

    tools: List[ToolResponse]
    total: int
    cached: bool = False  # True if tools were returned from cache

    class Config:
        json_schema_extra = {
            "example": {
                "tools": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "tool_name": "create_document",
                        "display_name": "Create Document",
                        "is_visible_to_oauth_clients": True
                    }
                ],
                "total": 1
            }
        }
