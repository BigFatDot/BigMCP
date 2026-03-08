"""
Tool Binding API endpoints.

Provides REST API for tool binding management and execution:
- Create/update/delete bindings
- List bindings for a context
- Execute bindings with parameter merging
- Get comprehensive binding information
- Copy bindings across contexts
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ..dependencies import get_current_user, get_current_organization
from ...services.tool_binding_service import ToolBindingService
from ...schemas.tool_binding import (
    ToolBindingCreate,
    ToolBindingUpdate,
    ToolBindingResponse,
    ToolBindingExecute,
    ToolBindingExecuteResponse,
    ToolBindingInfoResponse
)


router = APIRouter()


# Dependency to get tool binding service
async def get_tool_binding_service(
    db: AsyncSession = Depends(get_async_session)
) -> ToolBindingService:
    """Dependency to create tool binding service."""
    return ToolBindingService(db)


@router.post(
    "/",
    response_model=ToolBindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tool binding",
    description="Create a new tool binding with pre-filled parameters"
)
async def create_tool_binding(
    binding_data: ToolBindingCreate,
    request: Request,
    context_id: UUID = Query(..., description="Context UUID to bind the tool to"),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Create a new tool binding."""
    current_user, _ = auth
    membership, organization_id = org_context
    created_by = current_user.id

    try:
        binding = await service.create_binding(
            organization_id=organization_id,
            context_id=context_id,
            tool_id=binding_data.tool_id,
            binding_name=binding_data.binding_name,
            default_parameters=binding_data.default_parameters,
            locked_parameters=binding_data.locked_parameters,
            description=binding_data.description,
            custom_validation=binding_data.custom_validation,
            created_by=created_by
        )
        return ToolBindingResponse.model_validate(binding)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=List[ToolBindingResponse],
    summary="List tool bindings",
    description="Get all tool bindings for a context"
)
async def list_tool_bindings(
    request: Request,
    context_id: UUID = Query(..., description="Context UUID"),
    include_inherited: bool = Query(
        False,
        description="Whether to include bindings from ancestor contexts"
    ),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """List all tool bindings for a context."""
    current_user, _ = auth
    membership, organization_id = org_context

    # TODO: Service should verify context belongs to organization
    # For now, service will handle this check internally

    bindings = await service.list_bindings(
        context_id=context_id,
        include_inherited=include_inherited
    )
    return [ToolBindingResponse.model_validate(b) for b in bindings]


@router.get(
    "/{binding_id}",
    response_model=ToolBindingResponse,
    summary="Get tool binding",
    description="Get details of a specific tool binding"
)
async def get_tool_binding(
    binding_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Get a specific tool binding."""
    current_user, _ = auth
    membership, organization_id = org_context

    binding = await service.get_binding(binding_id)

    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    # Verify binding belongs to user's organization
    if binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    return ToolBindingResponse.model_validate(binding)


@router.get(
    "/{binding_id}/info",
    response_model=ToolBindingInfoResponse,
    summary="Get binding information",
    description="Get comprehensive binding information including tool and server details"
)
async def get_binding_info(
    binding_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Get comprehensive binding information."""
    current_user, _ = auth
    membership, organization_id = org_context

    # Verify binding belongs to user's organization
    binding = await service.get_binding(binding_id)
    if not binding or binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    try:
        info = await service.get_binding_info(binding_id)
        return ToolBindingInfoResponse.model_validate(info)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.patch(
    "/{binding_id}",
    response_model=ToolBindingResponse,
    summary="Update tool binding",
    description="Update tool binding configuration"
)
async def update_tool_binding(
    binding_id: UUID,
    binding_data: ToolBindingUpdate,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Update a tool binding."""
    current_user, _ = auth
    membership, organization_id = org_context

    # Verify binding exists and belongs to user's organization before updating
    binding = await service.get_binding(binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    # Verify binding belongs to user's organization
    if binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    try:
        binding = await service.update_binding(
            binding_id=binding_id,
            binding_name=binding_data.binding_name,
            description=binding_data.description,
            default_parameters=binding_data.default_parameters,
            locked_parameters=binding_data.locked_parameters,
            custom_validation=binding_data.custom_validation
        )
        return ToolBindingResponse.model_validate(binding)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tool binding",
    description="Delete a tool binding"
)
async def delete_tool_binding(
    binding_id: UUID,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Delete a tool binding."""
    current_user, _ = auth
    membership, organization_id = org_context

    # Verify binding exists and belongs to user's organization before deleting
    binding = await service.get_binding(binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    # Verify binding belongs to user's organization
    if binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    try:
        await service.delete_binding(binding_id)
        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post(
    "/{binding_id}/execute",
    response_model=ToolBindingExecuteResponse,
    summary="Execute tool binding",
    description="Execute a tool binding with merged parameters"
)
async def execute_tool_binding(
    binding_id: UUID,
    execution_data: ToolBindingExecute,
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Execute a tool binding."""
    current_user, _ = auth
    membership, organization_id = org_context

    # Verify binding belongs to user's organization before execution
    binding = await service.get_binding(binding_id)
    if not binding or binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    try:
        import time
        start_time = time.time()

        result = await service.execute_binding(
            binding_id=binding_id,
            user_parameters=execution_data.parameters
        )

        execution_time_ms = (time.time() - start_time) * 1000

        # Get binding info for response
        info = await service.get_binding_info(binding_id)

        return ToolBindingExecuteResponse(
            success=result.get("success", True),
            result=result.get("result"),
            execution_time_ms=execution_time_ms,
            error=None,
            binding_id=binding_id,
            binding_name=binding.binding_name,
            tool_name=info["tool"]["tool_name"] if info.get("tool") else "unknown",
            server_id=info["server"]["server_id"] if info.get("server") else "unknown",
            merged_parameters={**binding.default_parameters, **execution_data.parameters}
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        # Get binding info for error response
        info = await service.get_binding_info(binding_id)

        return ToolBindingExecuteResponse(
            success=False,
            result=None,
            execution_time_ms=0,
            error=str(e),
            binding_id=binding_id,
            binding_name=binding.binding_name,
            tool_name=info["tool"]["tool_name"] if info.get("tool") else "unknown",
            server_id=info["server"]["server_id"] if info.get("server") else "unknown",
            merged_parameters={**binding.default_parameters, **execution_data.parameters}
        )


@router.post(
    "/{binding_id}/copy",
    response_model=ToolBindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Copy tool binding",
    description="Copy a tool binding to a different context"
)
async def copy_tool_binding(
    binding_id: UUID,
    request: Request,
    new_context_id: UUID = Query(..., description="Target context UUID"),
    new_binding_name: Optional[str] = Query(
        None,
        description="New binding name (defaults to original)"
    ),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Copy a tool binding to a different context."""
    current_user, _ = auth
    membership, organization_id = org_context

    # Verify source binding belongs to user's organization
    binding = await service.get_binding(binding_id)
    if not binding or binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding {binding_id} not found"
        )

    try:
        new_binding = await service.copy_binding(
            binding_id=binding_id,
            new_context_id=new_context_id,
            new_binding_name=new_binding_name
        )
        return ToolBindingResponse.model_validate(new_binding)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/by-name/{binding_name}",
    response_model=ToolBindingResponse,
    summary="Get binding by name",
    description="Get a tool binding by name within a context"
)
async def get_binding_by_name(
    binding_name: str,
    request: Request,
    context_id: UUID = Query(..., description="Context UUID"),
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    service: ToolBindingService = Depends(get_tool_binding_service)
):
    """Get a tool binding by name within a context."""
    current_user, _ = auth
    membership, organization_id = org_context

    binding = await service.get_binding_by_name(
        context_id=context_id,
        binding_name=binding_name
    )

    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding '{binding_name}' not found in context {context_id}"
        )

    # Verify binding belongs to user's organization
    if binding.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool binding '{binding_name}' not found in context {context_id}"
        )

    return ToolBindingResponse.model_validate(binding)
