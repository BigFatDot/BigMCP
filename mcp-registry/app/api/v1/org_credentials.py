"""
Organization Credentials API endpoints.

Allows managing shared credentials for MCP servers.
- List: All Team members can list, but non-admins only see visible_to_users=True
- Create/Update/Delete: Admin/Owner only
- Shared across all users in the organization
- Used as fallback when user doesn't have personal credentials
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ...db.database import get_async_session
from ...models.user import User
from ...models.api_key import APIKey
from ...models.organization import UserRole
from ...models.mcp_server import MCPServer
from ..dependencies import get_current_user, get_current_admin_user, get_current_organization
from ...services.credential_service import CredentialService
from ...schemas.credential import (
    OrganizationCredentialCreate,
    OrganizationCredentialUpdate,
    OrganizationCredentialResponse
)
from ...core.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency to get credential service
async def get_credential_service(
    db: AsyncSession = Depends(get_async_session)
) -> CredentialService:
    """Dependency to create credential service."""
    return CredentialService(db)


@router.post(
    "/",
    response_model=OrganizationCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization credentials (Admin)",
    description="Create shared credentials for an MCP server (admin only)"
)
async def create_org_credential(
    credential_data: OrganizationCredentialCreate,
    current_user: User = Depends(get_current_admin_user),
    org_context: tuple = Depends(get_current_organization),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Create shared organization credentials for an MCP server.

    These credentials are:
    - Shared across all users in the organization
    - Hidden from regular users (controlled by visible_to_users flag)
    - Used as fallback when user doesn't have personal credentials

    Admin only.
    """
    # Get user's organization ID
    membership, organization_id = org_context
    created_by = current_user.id

    # Admin role verification done by get_current_admin_user dependency

    try:
        # Determine server_id: use provided UUID or create from marketplace
        final_server_id = credential_data.server_id

        if not final_server_id and credential_data.marketplace_server_id:
            # Auto-create MCPServer from marketplace
            from ...services.marketplace_service import get_marketplace_service
            from ...services.mcp_server_service import MCPServerService
            from ...models.mcp_server import InstallType
            from ...db.session import get_db

            marketplace = get_marketplace_service()
            server_data = await marketplace.get_server(credential_data.marketplace_server_id)

            if not server_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Marketplace server not found: {credential_data.marketplace_server_id}"
                )

            # Map install type
            install_type_map = {
                "npm": InstallType.NPM,
                "pip": InstallType.PIP,
                "github": InstallType.GITHUB,
                "docker": InstallType.DOCKER,
                "local": InstallType.LOCAL,
            }

            install_type = install_type_map.get(
                server_data.get("install_type", "npm"),
                InstallType.NPM
            )

            # Check if a TEAM server already exists (server with org credentials)
            # We only reuse servers that are already configured as Team Servers
            # Personal servers (user-created) should NOT be converted to team servers
            from sqlalchemy import select
            from ...models.mcp_server import MCPServer
            from ...models.user_credential import OrganizationCredential

            # Find servers with this marketplace ID that ALREADY have org credentials
            result = await service.db.execute(
                select(MCPServer)
                .join(OrganizationCredential, OrganizationCredential.server_id == MCPServer.id)
                .where(MCPServer.organization_id == organization_id)
                .where(OrganizationCredential.organization_id == organization_id)
                .where(MCPServer.env.op('@>')({"_MARKETPLACE_SERVER_ID": credential_data.marketplace_server_id}))
                .limit(1)
            )
            existing_team_server = result.scalar_one_or_none()

            if existing_team_server:
                # Use existing team server (already has org credentials)
                final_server_id = existing_team_server.id
                logger.info(f"Using existing Team MCPServer {final_server_id} for marketplace {credential_data.marketplace_server_id}")
            else:
                # Create new MCPServer dedicated to the Team
                mcp_service = MCPServerService(service.db)

                # Build env with marketplace ID and mark as team server
                server_env = {
                    "_MARKETPLACE_SERVER_ID": credential_data.marketplace_server_id,
                    "_IS_TEAM_SERVER": "true"
                }
                source_env = server_data.get("env", {})
                for key, value in source_env.items():
                    if isinstance(value, str) and not value.startswith("${"):
                        server_env[key] = value

                default_command = "uvx" if install_type == InstallType.PIP else "npx"

                # Use "team-" prefix for server_id to ensure uniqueness
                team_server_id = f"team-{credential_data.marketplace_server_id}"
                # Add " - Team" suffix to server name for clarity
                base_name = server_data.get('name', credential_data.marketplace_server_id)
                team_server_name = f"{base_name} - Team"

                new_server = await mcp_service.create_server(
                    organization_id=organization_id,
                    server_id=team_server_id,
                    name=team_server_name,
                    install_type=install_type,
                    install_package=server_data.get("install_package", ""),
                    command=server_data.get("command", default_command),
                    args=server_data.get("args", []),
                    env=server_env,
                    version=server_data.get("version"),
                    auto_start=False
                )

                final_server_id = new_server.id
                logger.info(f"Created new Team MCPServer {final_server_id} ({team_server_name}) for marketplace {credential_data.marketplace_server_id}")

        if not final_server_id:
            raise HTTPException(
                status_code=400,
                detail="Either server_id or marketplace_server_id must be provided"
            )

        credential = await service.create_org_credential(
            organization_id=organization_id,
            server_id=final_server_id,
            credentials=credential_data.credentials,
            name=credential_data.name,
            description=credential_data.description,
            visible_to_users=credential_data.visible_to_users,
            created_by=created_by
        )

        # Invalidate caches for all users in this organization
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        logger.info(f"Invalidated caches for org {organization_id} after org credential creation")

        # Restart running servers across all users in org to pick up new credentials
        try:
            from app.routers.mcp_unified import gateway
            # Get the server_id string from the server
            async with service.db.begin_nested():
                server_query = select(MCPServer).where(MCPServer.id == credential.server_id)
                server_result = await service.db.execute(server_query)
                server = server_result.scalar_one_or_none()
                if server:
                    await gateway.user_server_pool.restart_servers_for_org_credential(
                        server_id_str=server.server_id,
                        organization_id=organization_id
                    )
        except Exception as e:
            logger.warning(f"Failed to restart servers after org credential creation: {e}")

        response = OrganizationCredentialResponse.model_validate(credential)

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
    response_model=List[OrganizationCredentialResponse],
    summary="List organization credentials",
    description="Get organization credentials. Admins see all, members see only visible ones."
)
async def list_org_credentials(
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    org_context: tuple = Depends(get_current_organization),
    include_inactive: bool = Query(False, description="Include inactive credentials (admin only)"),
    show_masked: bool = Query(False, description="Include masked credentials in response (admin only)"),
    service: CredentialService = Depends(get_credential_service)
):
    """
    List organization credentials.

    Access control (like tool_groups pattern):
    - Admin/Owner: Returns ALL org credentials
    - Member/Viewer: Returns only credentials with visible_to_users=True
    """
    current_user, api_key = auth

    # Get user's organization ID and role
    membership, organization_id = org_context
    is_admin = membership.role in [UserRole.ADMIN, UserRole.OWNER]

    # Get credentials based on role
    credentials = await service.get_org_credentials(
        organization_id=organization_id,
        include_inactive=include_inactive if is_admin else False
    )

    # Filter for non-admins: only visible_to_users=True
    if not is_admin:
        credentials = [c for c in credentials if c.visible_to_users]

    responses = [OrganizationCredentialResponse.model_validate(c) for c in credentials]

    # Add masked credentials if requested (admin only)
    if show_masked and is_admin:
        secrets_manager = get_secrets_manager()
        for i, credential in enumerate(credentials):
            responses[i].credentials_masked = secrets_manager.mask_credentials(
                credential.credentials
            )

    return responses


@router.get(
    "/{server_id}",
    response_model=OrganizationCredentialResponse,
    summary="Get organization credential (Admin)",
    description="Get organization credentials for a specific MCP server (admin only)"
)
async def get_org_credential(
    server_id: UUID,
    current_user: User = Depends(get_current_admin_user),
    org_context: tuple = Depends(get_current_organization),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Get organization credentials for a specific MCP server.

    Admin only.
    """
    # Get user's organization ID
    membership, organization_id = org_context

    # Admin role verification done by get_current_admin_user dependency

    credential = await service._get_org_credential(organization_id, server_id)

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization credentials not found for server {server_id}"
        )

    response = OrganizationCredentialResponse.model_validate(credential)

    # Add masked credentials if requested
    if show_masked:
        secrets_manager = get_secrets_manager()
        response.credentials_masked = secrets_manager.mask_credentials(
            credential.credentials
        )

    return response


@router.patch(
    "/{server_id}",
    response_model=OrganizationCredentialResponse,
    summary="Update organization credential (Admin)",
    description="Update organization credentials for an MCP server (admin only)"
)
async def update_org_credential(
    server_id: UUID,
    credential_data: OrganizationCredentialUpdate,
    current_user: User = Depends(get_current_admin_user),
    org_context: tuple = Depends(get_current_organization),
    show_masked: bool = Query(False, description="Include masked credentials in response"),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Update organization credentials for an MCP server.

    Admin only.
    """
    # Get user's organization ID
    membership, organization_id = org_context
    updated_by = current_user.id

    # Admin role verification done by get_current_admin_user dependency

    try:
        credential = await service.update_org_credential(
            organization_id=organization_id,
            server_id=server_id,
            credentials=credential_data.credentials,
            name=credential_data.name,
            description=credential_data.description,
            visible_to_users=credential_data.visible_to_users,
            is_active=credential_data.is_active,
            updated_by=updated_by
        )

        # Invalidate caches for all users in this organization
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        logger.info(f"Invalidated caches for org {organization_id} after org credential update")

        # Restart running servers across all users in org to pick up new credentials
        try:
            from app.routers.mcp_unified import gateway
            # Get the server_id string from the server
            async with service.db.begin_nested():
                server_query = select(MCPServer).where(MCPServer.id == credential.server_id)
                server_result = await service.db.execute(server_query)
                server = server_result.scalar_one_or_none()
                if server:
                    await gateway.user_server_pool.restart_servers_for_org_credential(
                        server_id_str=server.server_id,
                        organization_id=organization_id
                    )
        except Exception as e:
            logger.warning(f"Failed to restart servers after org credential update: {e}")

        response = OrganizationCredentialResponse.model_validate(credential)

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
    "/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete organization credential (Admin)",
    description="Delete organization credentials for an MCP server (admin only)"
)
async def delete_org_credential(
    server_id: UUID,
    current_user: User = Depends(get_current_admin_user),
    org_context: tuple = Depends(get_current_organization),
    service: CredentialService = Depends(get_credential_service)
):
    """
    Delete organization credentials for an MCP server.

    Admin only.
    """
    # Get user's organization ID
    membership, organization_id = org_context

    # Admin role verification done by get_current_admin_user dependency

    try:
        # Get the server_id_str BEFORE deleting for restart logic
        db = service.db
        server_query = select(MCPServer).where(MCPServer.id == server_id)
        server_result = await db.execute(server_query)
        server_for_restart = server_result.scalar_one_or_none()
        server_id_str = server_for_restart.server_id if server_for_restart else None

        await service.delete_org_credential(organization_id, server_id)

        # Invalidate caches for all users in this organization
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(organization_id)
        logger.info(f"Invalidated caches for org {organization_id} after org credential deletion")

        # Restart running servers across all users in org (they'll use fallback or no credentials now)
        if server_id_str:
            try:
                from app.routers.mcp_unified import gateway
                await gateway.user_server_pool.restart_servers_for_org_credential(
                    server_id_str=server_id_str,
                    organization_id=organization_id
                )
            except Exception as e:
                logger.warning(f"Failed to restart servers after org credential deletion: {e}")

        # Check if ANY credentials (user or organization) remain for this server
        from app.models.user_credential import UserCredential, OrganizationCredential

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
