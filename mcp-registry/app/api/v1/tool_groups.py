"""
Tool Groups API endpoints.

Allows users to create specialized tool groups for AI agents,
controlling which tools are exposed to Claude Desktop.
"""

import logging
from uuid import UUID
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from ...db.database import get_async_session
from ...models.user import User
from ...models.tool_group import ToolGroupVisibility, ToolGroupItemType
from ...services.tool_group_service import ToolGroupService
from ...schemas.tool_group import (
    ToolGroupCreate,
    ToolGroupUpdate,
    ToolGroupResponse,
    ToolGroupListResponse,
    ToolGroupItemCreate,
    ToolGroupItemResponse,
    ToolInfoResponse
)
from ..dependencies import get_current_user_jwt, get_current_organization_jwt


router = APIRouter(prefix="/tool-groups", tags=["Tool Groups"])


# ===== Dependencies =====

async def get_tool_group_service(
    db: AsyncSession = Depends(get_async_session)
) -> ToolGroupService:
    """Get ToolGroupService instance."""
    return ToolGroupService(db)



# ===== Endpoints =====

@router.get(
    "",
    response_model=ToolGroupListResponse,
    summary="List tool groups",
    description="List all tool groups accessible to the current user"
)
async def list_tool_groups(
    include_org_groups: bool = Query(
        True,
        description="Include organization-visible groups (not just own groups)"
    ),
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    List tool groups for the current user.

    Returns:
        - User's private groups
        - Organization-visible groups (if include_org_groups=True)
    """
    _, org_id = org_context

    groups = await service.list_groups(
        user_id=user.id,
        organization_id=org_id,
        include_org_groups=include_org_groups
    )

    return ToolGroupListResponse(
        groups=[_group_to_response(g) for g in groups],
        total=len(groups)
    )


@router.post(
    "",
    response_model=ToolGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tool group",
    description="Create a new tool group"
)
async def create_tool_group(
    data: ToolGroupCreate,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Create a new tool group.

    The group starts empty - use POST /tool-groups/{id}/items to add tools.
    """
    _, org_id = org_context

    try:
        group = await service.create_group(
            user_id=user.id,
            organization_id=org_id,
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            visibility=data.visibility
        )
        return _group_to_response(group)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/available-tools",
    response_model=List[ToolInfoResponse],
    summary="List available tools",
    description="List all tools that can be added to groups"
)
async def list_available_tools(
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    List all tools available for adding to groups.

    Returns tools from all enabled MCP servers in the user's organization,
    along with which groups each tool is already in.
    """
    _, org_id = org_context

    tools = await service.list_available_tools(organization_id=org_id)

    return [
        ToolInfoResponse(
            id=t["id"],
            server_id=t["server_id"],
            server_name=t["server_name"],
            tool_name=t["tool_name"],
            display_name=t.get("display_name"),
            description=t.get("description"),
            category=t.get("category"),
            tags=t.get("tags"),
            in_groups=t.get("in_groups", []),
            is_visible_to_oauth_clients=t.get("is_visible_to_oauth_clients", False),
        )
        for t in tools
    ]


@router.get(
    "/{group_id}",
    response_model=ToolGroupResponse,
    summary="Get tool group",
    description="Get details of a specific tool group"
)
async def get_tool_group(
    group_id: UUID,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """Get a specific tool group by ID."""
    _, org_id = org_context

    group = await service.get_group(
        group_id=group_id,
        user_id=user.id,
        organization_id=org_id
    )

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool group not found or not accessible"
        )

    return _group_to_response(group)


@router.patch(
    "/{group_id}",
    response_model=ToolGroupResponse,
    summary="Update tool group",
    description="Update tool group metadata (owner only)"
)
async def update_tool_group(
    group_id: UUID,
    data: ToolGroupUpdate,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Update a tool group.

    Only the owner can update a group.
    """
    try:
        group = await service.update_group(
            group_id=group_id,
            user_id=user.id,
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            visibility=data.visibility,
            is_active=data.is_active
        )

        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tool group not found or you are not the owner"
            )

        return _group_to_response(group)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tool group",
    description="Delete a tool group (owner only)"
)
async def delete_tool_group(
    group_id: UUID,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Delete a tool group.

    Only the owner can delete a group.
    Warning: Any API keys linked to this group will lose their tool restriction.
    """
    success = await service.delete_group(
        group_id=group_id,
        user_id=user.id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool group not found or you are not the owner"
        )

    return None


@router.post(
    "/{group_id}/items",
    response_model=ToolGroupItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add tool to group",
    description="Add a tool to a tool group (owner only)"
)
async def add_item_to_group(
    group_id: UUID,
    data: ToolGroupItemCreate,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Add a tool to a group.

    Only the group owner can add items.
    """
    if data.item_type == ToolGroupItemType.TOOL:
        if not data.tool_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tool_id is required for item_type=TOOL"
            )

        try:
            item = await service.add_tool_to_group(
                group_id=group_id,
                tool_id=data.tool_id,
                user_id=user.id,
                order=data.order,
                config=data.config
            )

            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tool group not found or you are not the owner"
                )

            return ToolGroupItemResponse(
                id=item.id,
                tool_group_id=item.tool_group_id,
                item_type=item.item_type.value if hasattr(item.item_type, 'value') else item.item_type,
                tool_id=item.tool_id,
                composition_id=item.composition_id,
                order=item.order,
                config=item.config
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    else:
        # Composition support to be added later
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Composition items not yet supported"
        )


@router.delete(
    "/{group_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove item from group",
    description="Remove a tool from a tool group (owner only)"
)
async def remove_item_from_group(
    group_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user_jwt),
    service: ToolGroupService = Depends(get_tool_group_service)
):
    """
    Remove a tool from a group.

    Only the group owner can remove items.
    """
    success = await service.remove_item_from_group(
        group_id=group_id,
        item_id=item_id,
        user_id=user.id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or you are not the group owner"
        )

    return None


# ===== Helper Functions =====

def _group_to_response(group) -> ToolGroupResponse:
    """Convert ToolGroup model to response schema."""
    items = []
    for item in group.items:
        item_response = ToolGroupItemResponse(
            id=item.id,
            tool_group_id=item.tool_group_id,
            item_type=item.item_type.value if hasattr(item.item_type, 'value') else item.item_type,
            tool_id=item.tool_id,
            composition_id=item.composition_id,
            order=item.order,
            config=item.config,
            # Enriched fields
            tool_name=getattr(item, '_tool_name', None),
            tool_description=getattr(item, '_tool_description', None),
            server_id=getattr(item, '_server_id', None),
            server_name=getattr(item, '_server_name', None)
        )
        items.append(item_response)

    return ToolGroupResponse(
        id=group.id,
        user_id=group.user_id,
        organization_id=group.organization_id,
        name=group.name,
        description=group.description,
        icon=group.icon,
        color=group.color,
        visibility=group.visibility.value if hasattr(group.visibility, 'value') else group.visibility,
        is_active=group.is_active,
        usage_count=group.usage_count,
        last_used_at=group.last_used_at,
        items=items,
        created_at=group.created_at,
        updated_at=group.updated_at
    )


# =============================================================================
# LLM-FIRST TOOLBOX PROPOSAL
# =============================================================================

from pydantic import BaseModel, Field as _Field
from typing import Any, Dict


class ToolGroupProposeRequest(BaseModel):
    """Ask the LLM to propose a toolbox for a given intent / persona."""

    intent: str = _Field(..., min_length=4, max_length=2000)
    also_load_to_pool: bool = _Field(False, description="Hint for the UI; the endpoint itself does NOT mutate the pool.")
    candidate_limit: int = _Field(40, ge=5, le=80, description="How many top-scored tools to feed the LLM.")


class ProposedToolEntry(BaseModel):
    tool_id: str
    name: str
    server: Optional[str] = None
    rationale: Optional[str] = None


class ProposedCompositionSuggestion(BaseModel):
    name: str
    description: str
    rationale: Optional[str] = None


class ToolGroupProposeResponse(BaseModel):
    name: str
    description: str
    color: Optional[str] = None
    intent: str
    tools: List[ProposedToolEntry]
    candidate_count: int
    composition_suggestion: Optional[ProposedCompositionSuggestion] = None
    note: Optional[str] = None


@router.post(
    "/propose",
    response_model=ToolGroupProposeResponse,
    summary="Propose a toolbox draft from a NL intent",
    description=(
        "LLM-first toolbox builder. The user describes a persona / use-case "
        "/ recurring task; the assistant scores the org's tool catalog, "
        "picks 3–15 of them, and proposes a name + description for a new "
        "toolbox. Optionally suggests a multi-step composition when the "
        "intent calls for orchestration."
    ),
)
async def propose_toolbox(
    payload: ToolGroupProposeRequest,
    user: User = Depends(get_current_user_jwt),
    org_context: tuple = Depends(get_current_organization_jwt),
    db: AsyncSession = Depends(get_async_session),
):
    _membership, org_id = org_context

    # Phase 1 — pre-filter the catalog with the cheap textual scorer used by
    # /pool/suggest so we never feed 200+ tools to the LLM context.
    from ...routers.mcp_gateway.pool.pool_loader import (
        load_searchable_pool,
        score_entry,
    )
    from ...routers.mcp_gateway.pool.search_handler import _tokenize

    candidates = await load_searchable_pool(db, org_id)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No enabled servers in your organization. Connect at least one "
                "MCP server before composing a toolbox."
            ),
        )

    tokens = _tokenize(payload.intent)
    scored = []
    for entry in candidates:
        s = score_entry(tokens, entry)
        scored.append((s, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    # Always include some tools even when the textual score is 0 — the LLM
    # still has the intent text to reason from.
    top = [entry for _, entry in scored[: payload.candidate_limit]]

    # Phase 2 — single LLM call producing a structured JSON proposal.
    from ...routers.mcp_unified import gateway

    analyzer = gateway.orchestration_tools.intent_analyzer

    import json as _json

    catalog_payload = [
        {
            "id": e.id,
            "name": e.name,
            "server": e.server_name,
            "kind": e.kind,
            "description": (e.description or "")[:240],
        }
        for e in top
    ]

    prompt = (
        "You design reusable toolboxes for an MCP gateway. Given a user's "
        "intent or persona description, pick 3 to 15 tools from the catalog "
        "that best support that intent and propose a concise toolbox.\n\n"
        "Return ONLY a JSON object — no prose, no markdown fences. Schema:\n"
        "{\n"
        '  "name": "short toolbox name (max 60 chars)",\n'
        '  "description": "1-2 sentences explaining what this toolbox is for",\n'
        '  "color": "orange|blue|green|purple|red|gray",\n'
        '  "tool_ids": ["uuid", "uuid", ...],   // only IDs from the catalog below\n'
        '  "rationales": {"uuid": "why this tool fits", ...},   // optional\n'
        '  "composition_suggestion": null OR {  // include only if a multi-step workflow is genuinely useful\n'
        '    "name": "...", "description": "...", "rationale": "..."\n'
        "  }\n"
        "}\n\n"
        f"User intent: {payload.intent}\n\n"
        f"Catalog (top {len(catalog_payload)} candidates):\n"
        f"{_json.dumps(catalog_payload, ensure_ascii=False)}\n\n"
        "JSON:"
    )

    raw = ""
    parsed: Dict[str, Any] = {}
    try:
        chat_url = (
            f"{analyzer.llm_url}/chat/completions"
            if "/v1" in analyzer.llm_url
            else f"{analyzer.llm_url}/v1/chat/completions"
        )
        response = await analyzer.http_client.post(
            chat_url,
            json={
                "model": analyzer.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1200,
            },
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            # Strip optional ```json fences
            stripped = raw.split("```")
            raw = next(
                (s for s in stripped if s.strip() and not s.strip().lower().startswith("json")),
                raw,
            ).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        parsed = _json.loads(raw) if raw else {}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM proposal failed: {e}",
        )

    # Validate the LLM picked tool IDs that actually exist in the candidate set.
    valid_ids = {e.id for e in top}
    proposed_ids = [
        tid for tid in (parsed.get("tool_ids") or []) if isinstance(tid, str) and tid in valid_ids
    ]
    rationales = parsed.get("rationales") or {}

    # Build response objects.
    by_id = {e.id: e for e in top}
    tools_out: List[ProposedToolEntry] = []
    for tid in proposed_ids:
        e = by_id[tid]
        tools_out.append(
            ProposedToolEntry(
                tool_id=e.id,
                name=e.name,
                server=e.server_name,
                rationale=(rationales.get(tid) if isinstance(rationales, dict) else None),
            )
        )

    composition_block = parsed.get("composition_suggestion")
    composition_obj: Optional[ProposedCompositionSuggestion] = None
    if isinstance(composition_block, dict) and composition_block.get("name"):
        composition_obj = ProposedCompositionSuggestion(
            name=str(composition_block.get("name", ""))[:120],
            description=str(composition_block.get("description", ""))[:400],
            rationale=composition_block.get("rationale"),
        )

    # Audit the LLM call (read-only proposal — no DB mutation, but it
    # consumes external LLM quota and the intent is user data we want a
    # trace of for compliance / debugging).
    try:
        from ...services.audit_service import AuditService
        from ...models.audit_log import AuditAction

        await AuditService(db).log_action(
            action=AuditAction.TOOLBOX_PROPOSE,
            actor_id=user.id,
            organization_id=org_id,
            resource_type="toolbox",
            details={
                "candidate_count": len(top),
                "selected_count": len(tools_out),
                "intent_length": len(payload.intent),
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"toolbox propose audit failed: {e}")

    return ToolGroupProposeResponse(
        name=str(parsed.get("name") or "Custom toolbox")[:60],
        description=str(parsed.get("description") or payload.intent)[:300],
        color=str(parsed.get("color") or "orange"),
        intent=payload.intent,
        tools=tools_out,
        candidate_count=len(top),
        composition_suggestion=composition_obj,
        note=None if tools_out else "The LLM did not select any tool — try a more specific intent or check that your catalog covers it.",
    )
