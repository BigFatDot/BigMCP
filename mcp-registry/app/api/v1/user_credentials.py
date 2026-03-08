"""
User Credentials API endpoints.

Allows users to manage their personal credentials for MCP servers.
User credentials override organization-level credentials.
"""

import asyncio
import logging
from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ...models.mcp_server import MCPServer
from ..dependencies import get_current_user, get_current_organization
from ...services.credential_service import CredentialService
from ...schemas.credential import (
    UserCredentialCreate,
    UserCredentialUpdate,
    UserCredentialResponse
)
from ...core.secrets_manager import get_secrets_manager


router = APIRouter()


# Dependency to get credential service
async def get_credential_service(
    db: AsyncSession = Depends(get_async_session)
) -> CredentialService:
    """Dependency to create credential service."""
    return CredentialService(db)


@router.post(
    "/",
    response_model=UserCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user credentials",
    description="Create personal credentials for an MCP server"
)
async def create_user_credential(
    credential_data: UserCredentialCreate,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Create personal credentials for an MCP server.

    These credentials will be used instead of organization-level credentials
    when this user accesses the MCP server.
    """
    current_user, _ = auth
    membership, organization_id = org_context

    user_id = current_user.id

    try:
        credential = await service.create_user_credential(
            user_id=user_id,
            server_id=credential_data.server_id,
            organization_id=organization_id,
            credentials=credential_data.credentials,
            name=credential_data.name,
            description=credential_data.description
        )

        # Invalidate user's tool cache for immediate updates
        from ...services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        await tool_cache.invalidate(user_id)
        logger.info(f"Invalidated tool cache for user {user_id} after credential creation")

        # Restart running servers that use this credential to pick up new values
        try:
            from app.routers.mcp_unified import gateway
            # Get the server_id string from the server
            async with service.db.begin_nested():
                server_query = select(MCPServer).where(MCPServer.id == credential.server_id)
                server_result = await service.db.execute(server_query)
                server = server_result.scalar_one_or_none()
                if server:
                    await gateway.user_server_pool.restart_servers_for_credential(
                        user_id=user_id,
                        server_id_str=server.server_id,
                        organization_id=organization_id
                    )
        except Exception as e:
            logger.warning(f"Failed to restart servers after credential creation: {e}")

        response = UserCredentialResponse.model_validate(credential)

        # Add masked credentials if requested
        if show_masked:
            secrets_manager = get_secrets_manager()
            response.credentials_masked = secrets_manager.mask_credentials(
                credential.credentials
            )

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/",
    response_model=List[UserCredentialResponse],
    summary="List user credentials",
    description="Get all personal credentials for the current user"
)
async def list_user_credentials(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    include_inactive: bool = Query(False, description="Include inactive credentials"),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service),
    db: AsyncSession = Depends(get_async_session)
):
    """List all personal credentials for the current user."""
    current_user, _ = auth
    membership, organization_id = org_context

    user_id = current_user.id

    credentials = await service.get_user_credentials(
        user_id=user_id,
        organization_id=organization_id,
        include_inactive=include_inactive
    )

    # Fetch server status for all credentials
    server_ids = [c.server_id for c in credentials]
    servers_map: Dict[UUID, MCPServer] = {}
    if server_ids:
        query = select(MCPServer).where(MCPServer.id.in_(server_ids))
        result = await db.execute(query)
        servers = result.scalars().all()
        servers_map = {s.id: s for s in servers}

    responses = [UserCredentialResponse.model_validate(c) for c in credentials]

    # Add server status and masked credentials
    secrets_manager = get_secrets_manager() if show_masked else None
    for i, credential in enumerate(credentials):
        # Add server status info
        server = servers_map.get(credential.server_id)
        if server:
            responses[i].server_status = server.status.value if hasattr(server.status, 'value') else str(server.status)
            responses[i].server_enabled = server.enabled
            responses[i].is_visible_to_oauth_clients = server.is_visible_to_oauth_clients

        # Add masked credentials if requested
        if show_masked and secrets_manager:
            responses[i].credentials_masked = secrets_manager.mask_credentials(
                credential.credentials
            )

    return responses


@router.get(
    "/{server_id}",
    response_model=UserCredentialResponse,
    summary="Get user credential",
    description="Get personal credentials for a specific MCP server"
)
async def get_user_credential(
    server_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service),
    db: AsyncSession = Depends(get_async_session)
):
    """Get personal credentials for a specific MCP server."""
    current_user, _ = auth

    # Get user's organization ID
    if not current_user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization"
        )

    user_id = current_user.id

    credential = await service._get_user_credential(user_id, server_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User credentials not found for server {server_id}"
        )

    response = UserCredentialResponse.model_validate(credential)

    # Add server status info
    server = await db.get(MCPServer, server_id)
    if server:
        response.server_status = server.status.value if hasattr(server.status, 'value') else str(server.status)
        response.server_enabled = server.enabled
        response.is_visible_to_oauth_clients = server.is_visible_to_oauth_clients

    # Add masked credentials if requested
    if show_masked:
        secrets_manager = get_secrets_manager()
        response.credentials_masked = secrets_manager.mask_credentials(
            credential.credentials
        )

    return response


@router.patch(
    "/{server_id}",
    response_model=UserCredentialResponse,
    summary="Update user credential",
    description="Update personal credentials for an MCP server"
)
async def update_user_credential(
    server_id: UUID,
    credential_data: UserCredentialUpdate,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service)
):
    """Update personal credentials for an MCP server."""
    current_user, _ = auth

    # Get user's organization ID
    if not current_user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization"
        )

    user_id = current_user.id

    try:
        credential = await service.update_user_credential(
            user_id=user_id,
            server_id=server_id,
            credentials=credential_data.credentials,
            name=credential_data.name,
            description=credential_data.description,
            is_active=credential_data.is_active
        )

        # Invalidate user's tool cache for immediate updates
        from ...services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        await tool_cache.invalidate(user_id)
        logger.info(f"Invalidated tool cache for user {user_id} after credential update")

        # Restart running servers that use this credential to pick up new values
        try:
            from app.routers.mcp_unified import gateway
            # Get the server_id string from the server
            async with service.db.begin_nested():
                server_query = select(MCPServer).where(MCPServer.id == credential.server_id)
                server_result = await service.db.execute(server_query)
                server = server_result.scalar_one_or_none()
                if server:
                    # Get organization_id from user's membership
                    organization_id = current_user.organization_memberships[0].organization_id
                    await gateway.user_server_pool.restart_servers_for_credential(
                        user_id=user_id,
                        server_id_str=server.server_id,
                        organization_id=organization_id
                    )
        except Exception as e:
            logger.warning(f"Failed to restart servers after credential update: {e}")

        response = UserCredentialResponse.model_validate(credential)

        # Add masked credentials if requested
        if show_masked:
            secrets_manager = get_secrets_manager()
            response.credentials_masked = secrets_manager.mask_credentials(
                credential.credentials
            )

        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user credential",
    description="Delete personal credentials by credential ID"
)
async def delete_user_credential(
    credential_id: UUID,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Delete personal credentials by credential ID.

    This endpoint accepts the credential's own UUID (not the server UUID),
    which is required for multi-instance scenarios where a user may have
    multiple credentials for different instances of the same service.

    After deletion, if the user has no remaining credentials for the server,
    the running server instance is stopped and its tools are removed.
    """
    from app.routers.mcp_unified import gateway
    from app.models.user_credential import UserCredential

    current_user, _ = auth

    # Get user's organization ID
    if not current_user.organization_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization"
        )

    user_id = current_user.id

    try:
        # Get the credential first to know the server_id
        credential = await service.get_user_credential_by_id(user_id, credential_id)
        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        server_id = credential.server_id

        # Delete the credential
        await service.delete_user_credential_by_id(user_id, credential_id)

        # Check if user still has active credentials for this server
        db = service.db
        remaining_query = select(UserCredential).where(
            and_(
                UserCredential.user_id == user_id,
                UserCredential.server_id == server_id,
                UserCredential.is_active == True
            )
        ).limit(1)
        remaining_result = await db.execute(remaining_query)
        has_remaining = remaining_result.scalar_one_or_none() is not None

        # Invalidate user's tool cache so next request reflects the change
        from app.services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        await tool_cache.invalidate(user_id)
        logger.info(f"Invalidated tool cache for user {user_id} after credential deletion")

        # Notify SSE-connected clients (e.g. Claude Desktop) that tools changed.
        # This pushes notifications/tools/list_changed so clients refresh immediately.
        try:
            org_membership = (
                current_user.organization_memberships[0]
                if current_user.organization_memberships else None
            )
            if org_membership:
                from app.routers.mcp_unified import notify_org_tools_changed
                asyncio.create_task(notify_org_tools_changed(org_membership.organization_id))
                logger.info(f"Scheduled tools/list_changed notification for org {org_membership.organization_id}")
        except Exception as e:
            logger.warning(f"Could not schedule tools notification after credential deletion: {e}")

        # Stop the running server if no credentials remain for this user
        if not has_remaining:
            try:
                await gateway.user_server_pool.stop_user_server(
                    user_id=user_id,
                    server_id=server_id
                )
                logger.info(f"Stopped server {server_id} for user {user_id} after credential deletion")
            except Exception as e:
                # Server might not be running, that's OK
                logger.debug(f"Could not stop server {server_id}: {e}")

        # Check if ANY credentials (user or organization) remain for this server
        from app.models.user_credential import OrganizationCredential

        # Count all credentials for this server
        user_creds_count = await db.scalar(
            select(func.count()).select_from(UserCredential).where(UserCredential.server_id == server_id)
        )
        org_creds_count = await db.scalar(
            select(func.count()).select_from(OrganizationCredential).where(OrganizationCredential.server_id == server_id)
        )

        # If no credentials remain at all, delete the server
        if user_creds_count == 0 and org_creds_count == 0:
            try:
                server_query = select(MCPServer).where(MCPServer.id == server_id)
                server_result = await db.execute(server_query)
                server = server_result.scalar_one_or_none()

                if server:
                    await db.delete(server)
                    await db.commit()
                    logger.info(f"Deleted server {server_id} after all credentials were removed")
            except Exception as e:
                logger.error(f"Failed to delete server {server_id}: {e}")
                # Don't raise - credential deletion was successful

        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
