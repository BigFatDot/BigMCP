"""Pydantic schemas for the composition executions API (Phase B-0).

Two surfaces:

- REST endpoints under ``/api/v1/compositions/executions`` use the
  ``ExecutionSummary`` (list view) and ``ExecutionDetail`` (single
  row + recent events) shapes.

- The MCP resource ``composition://executions/{id}`` returns
  ``ExecutionResourcePayload`` serialised as JSON in the
  ``resources/read`` text content.

The handler that writes the MCP resource payload also computes
``result_uri`` (only set when ``status='completed'``) so clients
have a stable URI to point at.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionSummary(BaseModel):
    """Compact row used in the list view + table UI.

    Excludes ``state`` and ``client_capabilities`` to keep the
    response small (a busy user can have hundreds of executions).
    Full state via ``ExecutionDetail`` or the MCP resource read.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    composition_id: UUID
    user_id: UUID
    organization_id: UUID
    parent_execution_id: Optional[UUID] = None
    status: str
    trigger: str
    cancel_requested: bool
    started_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    error: Optional[str] = None
    # Convenience derived fields populated by the route handler
    current_step_id: Optional[str] = None
    suspension_reason: Optional[str] = None


class ExecutionStepEventOut(BaseModel):
    """One row of the timeline rendered in the detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    step_id: str
    event_type: str
    payload: Optional[Dict[str, Any]] = None
    timestamp: datetime


class ExecutionDetail(ExecutionSummary):
    """Full execution row + recent step events for the detail page."""

    state: Dict[str, Any]
    client_capabilities: Optional[Dict[str, Any]] = None
    mcp_session_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    events: List[ExecutionStepEventOut] = Field(default_factory=list)


class ExecutionListResponse(BaseModel):
    """Paginated list of executions."""

    items: List[ExecutionSummary]
    total: int
    limit: int
    offset: int


class ResumeRequest(BaseModel):
    """Body of ``POST /executions/{id}/resume``.

    In B-0 this only fires for ``_test_suspend`` (debug). The
    ``response`` is injected as the suspended step's result, so the
    shape is intentionally free-form. B-1+ step types will validate
    the response against the suspended step's schema (e.g., elicit
    schema, wait_callback expected_schema).
    """

    response: Any = Field(
        ...,
        description=(
            "The value to inject as the suspended step's result. "
            "Free-form in B-0; B-1+ step types validate against "
            "their declared schema."
        ),
    )


class ExecutionResourcePayload(BaseModel):
    """Body of the MCP resource ``composition://executions/{id}``.

    Read from ``resources/read``; the JSON-encoded form is wrapped
    in the spec's ``{uri, mimeType, text}`` envelope by the handler.
    """

    execution_id: UUID
    status: str
    current_step_id: Optional[str] = None
    step_results: Dict[str, Any] = Field(default_factory=dict)
    step_status: Dict[str, str] = Field(default_factory=dict)
    suspension: Optional[Dict[str, Any]] = None
    started_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # Set when status='completed' so subscribers have a stable URI
    # to point at after the final notification.
    result_uri: Optional[str] = None


class CompositionStatusInput(BaseModel):
    """Input schema for the ``composition_status`` MCP meta-tool."""

    execution_id: str = Field(
        ..., description="UUID returned by composition tool call"
    )


class CompositionStatusOutput(BaseModel):
    """Output schema for the ``composition_status`` MCP meta-tool.

    Returns a SUMMARY only — full step results are intentionally
    omitted to keep polls cheap. For full state, the client should
    read the MCP resource or call the REST detail endpoint.

    A ``status='not_found'`` response is returned both when the
    execution doesn't exist AND when it belongs to another user
    (no info leak).
    """

    execution_id: str
    status: str  # queued | running | suspended | completed | failed | expired | cancelled | not_found
    current_step_id: Optional[str] = None
    suspension_reason: Optional[str] = None
    error: Optional[str] = None
    expires_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    result_uri: Optional[str] = None
