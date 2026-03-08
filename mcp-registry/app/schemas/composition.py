"""
Pydantic schemas for Composition API.

Defines request/response schemas for workflow compositions.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field

from ..models.composition import CompositionStatus, CompositionVisibility


# =============================================================================
# STEP & MAPPING SCHEMAS
# =============================================================================

class CompositionStep(BaseModel):
    """Schema for a single workflow step."""

    id: str = Field(..., description="Unique step identifier")
    tool: str = Field(..., description="Tool name to execute")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters to pass to the tool"
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="Step IDs this step depends on"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "step1",
                "tool": "grist_fetch_record",
                "params": {"table_id": "Projects", "record_id": "${input.record_id}"},
                "depends_on": []
            }
        }


class DataMapping(BaseModel):
    """Schema for data flow mapping between steps."""

    from_path: str = Field(..., alias="from", description="Source path (e.g., 'step1.output.title')")
    to_path: str = Field(..., alias="to", description="Target path (e.g., 'step2.input.title')")

    class Config:
        populate_by_name = True


class StepResultSchema(BaseModel):
    """Schema for individual step execution result."""

    step_id: str = Field(..., description="Unique step identifier")
    tool: str = Field(..., description="Tool name that was executed")
    status: str = Field(..., description="Step status: success, failed, or skipped")
    duration_ms: int = Field(..., description="Step execution duration in milliseconds")
    result: Optional[Dict[str, Any]] = Field(
        None,
        description="Step output if successful"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if step failed"
    )
    retries: int = Field(
        default=0,
        description="Number of retry attempts"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "step_id": "fetch_data",
                "tool": "grist_fetch_record",
                "status": "success",
                "duration_ms": 234,
                "result": {"id": "123", "name": "Test"},
                "error": None,
                "retries": 0
            }
        }


# =============================================================================
# CREATE / UPDATE SCHEMAS
# =============================================================================

class CompositionCreate(BaseModel):
    """Schema for creating a composition."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the composition"
    )
    description: Optional[str] = Field(
        None,
        description="Description of what this composition does"
    )
    visibility: str = Field(
        default=CompositionVisibility.PRIVATE.value,
        description="Visibility: private (creator only), organization (team), public (future)"
    )
    steps: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Workflow steps"
    )
    data_mappings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Data flow mappings between steps"
    )
    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for composition inputs"
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON Schema for composition outputs"
    )
    server_bindings: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps logical server IDs to actual server UUIDs"
    )
    allowed_roles: List[str] = Field(
        default_factory=list,
        description="Roles allowed to execute (empty = all except viewer)"
    )
    force_org_credentials: bool = Field(
        default=False,
        description="Use org credentials instead of user credentials"
    )
    status: str = Field(
        default=CompositionStatus.TEMPORARY.value,
        description="Lifecycle status"
    )
    ttl: Optional[int] = Field(
        None,
        description="Time-to-live in seconds (for temporary compositions)"
    )
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (tags, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "GitHub Issue from Grist",
                "description": "Creates a GitHub issue from a Grist record",
                "steps": [
                    {"id": "fetch", "tool": "grist_fetch_record", "params": {"table_id": "Issues"}},
                    {"id": "create", "tool": "github_create_issue", "params": {}, "depends_on": ["fetch"]}
                ],
                "data_mappings": [
                    {"from": "fetch.output.title", "to": "create.input.title"}
                ],
                "server_bindings": {"grist": "uuid-grist", "github": "uuid-github"},
                "allowed_roles": [],
                "status": "temporary"
            }
        }


class CompositionUpdate(BaseModel):
    """Schema for updating a composition."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Optional[str] = Field(None, description="Visibility: private, organization, public")
    steps: Optional[List[Dict[str, Any]]] = None
    data_mappings: Optional[List[Dict[str, Any]]] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    server_bindings: Optional[Dict[str, str]] = None
    allowed_roles: Optional[List[str]] = None
    force_org_credentials: Optional[bool] = None
    status: Optional[str] = None
    ttl: Optional[int] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class CompositionPromote(BaseModel):
    """Schema for promoting a composition status."""

    status: str = Field(
        ...,
        description="Target status: validated or production"
    )

    class Config:
        json_schema_extra = {
            "example": {"status": "validated"}
        }


# =============================================================================
# RESPONSE SCHEMAS
# =============================================================================

class CompositionResponse(BaseModel):
    """Schema for composition response."""

    id: UUID
    organization_id: UUID
    created_by: UUID
    name: str
    description: Optional[str]
    visibility: str
    steps: List[Dict[str, Any]]
    data_mappings: List[Dict[str, Any]]
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    server_bindings: Dict[str, Any]
    allowed_roles: List[str]
    force_org_credentials: bool
    requires_approval: bool
    status: str
    ttl: Optional[int]
    extra_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    # Computed fields (added by API)
    can_execute: Optional[bool] = None
    can_edit: Optional[bool] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "organization_id": "123e4567-e89b-12d3-a456-426614174001",
                "created_by": "123e4567-e89b-12d3-a456-426614174002",
                "name": "GitHub Issue from Grist",
                "description": "Creates a GitHub issue from a Grist record",
                "steps": [],
                "data_mappings": [],
                "input_schema": {},
                "output_schema": None,
                "server_bindings": {},
                "allowed_roles": [],
                "force_org_credentials": False,
                "requires_approval": False,
                "status": "validated",
                "ttl": None,
                "extra_metadata": {"execution_count": 42},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "can_execute": True,
                "can_edit": True
            }
        }


class CompositionListResponse(BaseModel):
    """Schema for list of compositions."""

    compositions: List[CompositionResponse]
    total: int


class CompositionExecuteRequest(BaseModel):
    """Schema for executing a composition."""

    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input values for the composition"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "inputs": {"record_id": "123", "project_name": "MyProject"}
            }
        }


class CompositionExecuteResponse(BaseModel):
    """Schema for composition execution result."""

    composition_id: UUID = Field(..., description="ID of the executed composition")
    execution_id: Optional[str] = Field(
        None,
        description="Unique execution identifier"
    )
    status: str = Field(
        ...,
        description="Execution status: success, partial, or failed"
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Final composition outputs (result of last successful step)"
    )
    duration_ms: int = Field(
        ...,
        description="Total execution duration in milliseconds"
    )
    step_results: List[StepResultSchema] = Field(
        default_factory=list,
        description="Detailed results from each step"
    )
    started_at: Optional[datetime] = Field(
        None,
        description="Execution start timestamp"
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="Execution completion timestamp"
    )
    error: Optional[str] = Field(
        None,
        description="Global error message if execution failed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "composition_id": "123e4567-e89b-12d3-a456-426614174000",
                "execution_id": "exec-abc123",
                "status": "success",
                "outputs": {"issue_url": "https://github.com/org/repo/issues/42"},
                "duration_ms": 1234,
                "step_results": [
                    {
                        "step_id": "fetch",
                        "tool": "grist_fetch_record",
                        "status": "success",
                        "duration_ms": 234,
                        "result": {"title": "My Issue"},
                        "error": None,
                        "retries": 0
                    },
                    {
                        "step_id": "create",
                        "tool": "github_create_issue",
                        "status": "success",
                        "duration_ms": 1000,
                        "result": {"url": "https://github.com/..."},
                        "error": None,
                        "retries": 0
                    }
                ],
                "started_at": "2024-01-15T10:30:00Z",
                "completed_at": "2024-01-15T10:30:01Z",
                "error": None
            }
        }
