"""
Pydantic schemas for Tool Binding API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class ToolBindingCreate(BaseModel):
    """Schema for creating a tool binding."""

    tool_id: UUID = Field(
        ...,
        description="Tool UUID to bind"
    )
    binding_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-friendly name for this binding"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description"
    )
    default_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pre-filled parameters merged with user params"
    )
    locked_parameters: List[str] = Field(
        default_factory=list,
        description="Parameters that cannot be overridden by user"
    )
    custom_validation: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional validation rules"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "tool_id": "123e4567-e89b-12d3-a456-426614174000",
                "binding_name": "create_doc",
                "description": "Create document in Project X",
                "default_parameters": {
                    "base_url": "https://docs.colaig.fr",
                    "project_id": "project-x-uuid"
                },
                "locked_parameters": ["base_url", "project_id"],
                "custom_validation": None
            }
        }


class ToolBindingUpdate(BaseModel):
    """Schema for updating a tool binding."""

    binding_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="New binding name"
    )
    description: Optional[str] = Field(
        None,
        description="New description"
    )
    default_parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="New default parameters (replaces existing)"
    )
    locked_parameters: Optional[List[str]] = Field(
        None,
        description="New locked parameters (replaces existing)"
    )
    custom_validation: Optional[Dict[str, Any]] = Field(
        None,
        description="New custom validation rules"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "description": "Updated description",
                "default_parameters": {
                    "base_url": "https://docs.colaig.fr",
                    "project_id": "new-project-uuid"
                }
            }
        }


class ToolBindingResponse(BaseModel):
    """Schema for tool binding response."""

    id: UUID
    organization_id: UUID
    context_id: UUID
    tool_id: UUID

    binding_name: str
    description: Optional[str]

    default_parameters: Dict[str, Any]
    locked_parameters: List[str]
    custom_validation: Optional[Dict[str, Any]]

    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "organization_id": "123e4567-e89b-12d3-a456-426614174001",
                "context_id": "123e4567-e89b-12d3-a456-426614174002",
                "tool_id": "123e4567-e89b-12d3-a456-426614174003",
                "binding_name": "create_doc",
                "description": "Create document in Project X",
                "default_parameters": {
                    "base_url": "https://docs.colaig.fr",
                    "project_id": "project-x-uuid"
                },
                "locked_parameters": ["base_url", "project_id"],
                "custom_validation": None,
                "created_by": "123e4567-e89b-12d3-a456-426614174004",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class ToolBindingExecute(BaseModel):
    """Schema for executing a tool binding."""

    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="User-provided parameters (merged with defaults)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "parameters": {
                    "title": "Meeting Notes",
                    "content": "Discussion about Q1 planning..."
                }
            }
        }


class ToolBindingExecuteResponse(BaseModel):
    """Schema for tool binding execution response."""

    success: bool
    result: Any
    execution_time_ms: Optional[float]
    error: Optional[str]

    # Metadata
    binding_id: UUID
    binding_name: str
    tool_name: str
    server_id: str

    # Parameters used
    merged_parameters: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "result": {
                    "document_id": "doc-123",
                    "url": "https://docs.colaig.fr/doc-123"
                },
                "execution_time_ms": 245.3,
                "error": None,
                "binding_id": "123e4567-e89b-12d3-a456-426614174000",
                "binding_name": "create_doc",
                "tool_name": "create_document",
                "server_id": "grist-mcp",
                "merged_parameters": {
                    "base_url": "https://docs.colaig.fr",
                    "project_id": "project-x-uuid",
                    "title": "Meeting Notes",
                    "content": "Discussion about Q1 planning..."
                }
            }
        }


class ToolBindingInfoResponse(BaseModel):
    """Schema for comprehensive tool binding information."""

    binding: ToolBindingResponse
    tool: Optional[Dict[str, Any]]
    server: Optional[Dict[str, Any]]
    context: Optional[Dict[str, Any]]

    # Computed fields
    available_parameters: Dict[str, Any]
    pre_filled_parameters: List[str]
    locked_parameters: List[str]
    user_must_provide: List[str]

    class Config:
        json_schema_extra = {
            "example": {
                "binding": {
                    "id": "...",
                    "binding_name": "create_doc"
                },
                "tool": {
                    "id": "...",
                    "tool_name": "create_document",
                    "description": "Create a document"
                },
                "server": {
                    "id": "...",
                    "server_id": "grist-mcp",
                    "status": "running"
                },
                "context": {
                    "id": "...",
                    "path": "root.team_alpha.project_x"
                },
                "available_parameters": {
                    "base_url": {"type": "string"},
                    "project_id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"}
                },
                "pre_filled_parameters": ["base_url", "project_id"],
                "locked_parameters": ["base_url", "project_id"],
                "user_must_provide": ["title", "content"]
            }
        }
