"""
Marketplace API Endpoints.

Provides endpoints for:
- Browsing available MCP servers
- Searching and filtering
- Getting installation instructions
- Triggering sync
- Installing servers to organization
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, status
from pydantic import BaseModel, Field

from ...services.marketplace_service import (
    get_marketplace_service,
    MarketplaceSyncService,
    ServerSource
)
from ...services.mcp_server_service import MCPServerService
from ...services.credential_service import CredentialService
from ...models.mcp_server import InstallType
from ...db.session import get_db
from ..dependencies import get_current_user, require_instance_admin
from ...models.user import User
from ...models.api_key import APIKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


# ============================================================================
# Pydantic Models
# ============================================================================

class MarketplaceServerResponse(BaseModel):
    """Response model for a marketplace server."""
    id: str
    name: str
    description: str
    install_type: str
    install_package: str
    command: Optional[str] = None
    args: list = []
    source: str
    source_url: Optional[str] = None
    repository: Optional[str] = None
    author: Optional[str] = None
    version: Optional[str] = None
    icon_url: Optional[str] = None
    requires_credentials: bool = False
    credentials: list = []
    category: Optional[str] = None
    tags: list = []
    verified: bool = False
    popularity: int = 0
    tools: list = []  # Full tool details [{name, description, is_read_only, ...}]
    tools_preview: list = []  # Just names for quick display
    requires_local_access: bool = False  # True if server needs local filesystem/docker access
    is_curated: bool = False  # True if from bigmcp_source.json (curated data)
    is_available: bool = True  # False if package doesn't exist (404)
    availability_reason: Optional[str] = None  # Reason if unavailable
    has_dynamic_tools: bool = False  # True if tools are loaded dynamically at runtime
    last_updated: Optional[str] = None
    discovered_at: Optional[str] = None


class MarketplaceListResponse(BaseModel):
    """Response model for paginated server list."""
    servers: list
    total: int
    offset: int
    limit: int
    has_more: bool


class CategoryResponse(BaseModel):
    """Response model for a category."""
    id: str
    name: str
    count: int


class SyncStatusResponse(BaseModel):
    """Response model for sync status."""
    servers_count: int
    last_sync: Optional[str] = None
    cache_expires: Optional[str] = None
    cache_valid: bool
    sources_enabled: dict
    sources_active: list


class SyncResultResponse(BaseModel):
    """Response model for sync result with integrated curation pipeline."""
    status: str
    sources: Optional[dict] = None
    total_fetched: Optional[int] = None
    total_after_dedup: Optional[int] = None
    servers_count: Optional[int] = None  # For cached responses
    sync_time: Optional[float] = None
    cache_expires: Optional[str] = None
    # Curation statistics
    curation: Optional[dict] = None  # {new_curated, from_cache, errors}
    # Deduplication statistics
    deduplication: Optional[dict] = None  # {unique_services, duplicates_removed}
    # Custom servers count
    custom_servers: Optional[int] = None


class InstallServerRequest(BaseModel):
    """Request model for installing a server."""
    server_id: str = Field(..., description="Marketplace server ID to install")
    organization_id: UUID = Field(..., description="Organization to install to")
    custom_env: Optional[dict] = Field(default=None, description="Custom environment variables")
    auto_start: bool = Field(default=False, description="Start server after installation")


class InstallServerResponse(BaseModel):
    """Response model for server installation."""
    success: bool
    message: str
    server_id: Optional[str] = None
    server_uuid: Optional[str] = None


class ConnectServerRequest(BaseModel):
    """Request model for connecting to a server (install + credentials)."""
    server_id: str = Field(..., description="Marketplace server ID to connect (e.g., 'grist-mcp')")
    organization_id: UUID = Field(..., description="Organization to install to")
    credentials: dict = Field(default={}, description="Credentials for the server (e.g., {'API_KEY': 'secret'})")
    name: Optional[str] = Field(None, description="Optional name for the credential set")
    auto_start: bool = Field(default=False, description="Start server after connection")
    use_org_credentials: bool = Field(default=False, description="Use organization credentials instead of creating new user credentials")
    additional_credentials: dict = Field(default={}, description="Additional credentials to merge with org credentials (for partial configs)")


class ConnectServerResponse(BaseModel):
    """Response model for server connection."""
    success: bool
    message: str
    server_id: str
    server_uuid: str
    credential_id: str
    already_installed: bool


# ============================================================================
# Dependencies
# ============================================================================

def get_marketplace() -> MarketplaceSyncService:
    """Get marketplace service instance."""
    return get_marketplace_service()


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/servers", response_model=MarketplaceListResponse)
async def list_servers(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in name/description/tags"),
    source: Optional[str] = Query(None, description="Filter by source (official, npm, github, local)"),
    verified_only: bool = Query(False, description="Only return verified servers"),
    saas_compatible: bool = Query(False, description="Only return servers compatible with SaaS (no local filesystem access required)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    List available MCP servers from the marketplace.

    Aggregates servers from multiple sources:
    - Local curated registry
    - GitHub (official modelcontextprotocol/servers)
    - npm registry (@modelcontextprotocol/*)

    Results are sorted by popularity (descending).

    Use `saas_compatible=true` to filter out servers that require local access
    (filesystem, docker, sqlite, etc.) which cannot work in cloud SaaS mode.
    """
    try:
        # Convert source string to enum if provided
        source_enum = None
        if source:
            try:
                source_enum = ServerSource(source.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid source: {source}. Valid values: {[s.value for s in ServerSource]}"
                )

        result = await marketplace.list_servers(
            category=category,
            search=search,
            source=source_enum,
            verified_only=verified_only,
            saas_compatible=saas_compatible,
            offset=offset,
            limit=limit
        )

        return MarketplaceListResponse(**result)

    except Exception as e:
        logger.error(f"Error listing marketplace servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servers/{server_id}")
async def get_server(
    server_id: str,
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    Get detailed information for a specific marketplace server.

    Returns installation instructions, required credentials, and tool preview.
    """
    try:
        server = await marketplace.get_server(server_id)

        if not server:
            raise HTTPException(
                status_code=404,
                detail=f"Server not found: {server_id}"
            )

        return server

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting marketplace server {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories", response_model=list)
async def list_categories(
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    List all server categories with counts.

    Categories are derived from server metadata.
    """
    try:
        categories = await marketplace.get_categories()
        return categories

    except Exception as e:
        logger.error(f"Error listing categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    Get current marketplace sync status.

    Shows:
    - Number of servers cached
    - Last sync timestamp
    - Cache expiration
    - Enabled sources
    """
    try:
        status = await marketplace.get_sync_status()
        return SyncStatusResponse(**status)

    except Exception as e:
        logger.error(f"Error getting sync status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connection-status")
async def get_connection_status(
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    Check if marketplace backend is connected and operational.

    Returns:
    - connected: True if marketplace is accessible
    - message: Status message
    - server_count: Number of servers available
    """
    try:
        status = await marketplace.get_sync_status()
        return {
            "connected": True,
            "message": "Marketplace connected",
            "server_count": status.get("server_count", 0)
        }
    except Exception as e:
        logger.error(f"Error checking connection status: {e}", exc_info=True)
        return {
            "connected": False,
            "message": str(e),
            "server_count": 0
        }


@router.post("/sync", response_model=SyncResultResponse)
async def trigger_sync(
    force: bool = Query(False, description="Force sync even if cache is valid"),
    background_tasks: BackgroundTasks = None,
    marketplace: MarketplaceSyncService = Depends(get_marketplace),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Trigger marketplace synchronization.

    **Requires: Instance Admin privileges**

    By default, uses cache if still valid. Set force=true to force refresh.

    Sources synchronized:
    - Local curated registry
    - GitHub official servers
    - npm registry
    """
    try:
        result = await marketplace.sync(force=force)
        return SyncResultResponse(**result)

    except Exception as e:
        logger.error(f"Error during marketplace sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SyncAndPersistResponse(BaseModel):
    """Response model for sync with persistence."""
    sync: dict
    persistence: dict


@router.post("/sync-and-persist", response_model=SyncAndPersistResponse)
async def sync_and_persist(
    force: bool = Query(False, description="Force sync even if cache is valid"),
    persist: bool = Query(True, description="Persist validated data to local registry"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Sync marketplace AND persist to marketplace_registry.json.

    **Requires: Instance Admin privileges**

    This is the recommended sync method for production. It:
    1. Loads servers from bigmcp_source.json (READ-ONLY source of truth)
    2. Fetches from external sources (official, npm, github)
    3. Deduplicates external sources against bigmcp and each other
    4. Adds custom servers from mcp_servers.json (never deduplicated)
    5. Applies curated enrichments (icons, service_id, etc.)
    6. Persists result to marketplace_registry.json (editable cache)

    Architecture:
    - bigmcp_source.json: READ-ONLY curated source (~158 servers)
    - mcp_servers.json: Custom servers (admin-added)
    - marketplace_registry.json: Persisted marketplace output (editable)

    Benefits:
    - Faster startup (load from cache instead of rebuilding)
    - Validated icons, credentials, and service_ids are preserved
    - External sources enrichments saved to editable file
    - Custom servers always preserved (never deduplicated)
    """
    try:
        result = await marketplace.sync_and_persist(force=force, persist=persist)
        return SyncAndPersistResponse(**result)
    except Exception as e:
        logger.error(f"Error during sync and persist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persist-validated")
async def persist_validated_servers(
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Persist current marketplace state to marketplace_registry.json.

    **Requires: Instance Admin privileges**

    Saves the current in-memory marketplace to marketplace_registry.json:
    - All servers with enriched metadata
    - Icons (iconUrl resolved from CDNs)
    - Service identifiers (serviceId from curation)
    - Credentials and tools
    - Categories and statistics

    Note: bigmcp_source.json is NOT modified (READ-ONLY).
    Results are saved to marketplace_registry.json (editable cache).
    """
    try:
        result = await marketplace.persist_validated_servers()
        return result
    except Exception as e:
        logger.error(f"Error persisting validated servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install", response_model=InstallServerResponse)
async def install_server(
    request: InstallServerRequest,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    marketplace: MarketplaceSyncService = Depends(get_marketplace),
    db=Depends(get_db)
):
    """
    Install a marketplace server to an organization.

    Creates an MCP server configuration from the marketplace template.
    Optionally starts the server after installation.

    Required credentials should be provided via custom_env or configured
    separately after installation.

    Requires authentication. User must be a member of the target organization.
    """
    current_user, _ = auth

    # Validate user belongs to the target organization
    user_org_ids = [m.organization_id for m in current_user.organization_memberships]
    if request.organization_id not in user_org_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization"
        )

    try:
        # Get server from marketplace
        server_data = await marketplace.get_server(request.server_id)

        if not server_data:
            raise HTTPException(
                status_code=404,
                detail=f"Server not found in marketplace: {request.server_id}"
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

        # Build environment from credentials and custom_env
        env = {}

        # Add custom environment variables
        if request.custom_env:
            env.update(request.custom_env)

        # Create MCP server via service
        mcp_service = MCPServerService(db)

        # Determine default command based on install type
        default_command = "uvx" if install_type == InstallType.PIP else "npx"

        server = await mcp_service.create_server(
            organization_id=request.organization_id,
            server_id=request.server_id,
            name=server_data.get("name", request.server_id),
            install_type=install_type,
            install_package=server_data.get("install_package", ""),
            command=server_data.get("command", default_command),
            args=server_data.get("args", []),
            env=env,
            version=server_data.get("version"),
            auto_start=request.auto_start
        )

        # Invalidate caches for all users in this organization
        from ...services.organization_tool_cache import tool_cache
        from ...services.user_tool_cache import get_user_tool_cache
        await tool_cache.invalidate_organization(request.organization_id)
        user_cache = get_user_tool_cache()
        await user_cache.invalidate_organization(request.organization_id)
        logger.info(f"Invalidated caches for org {request.organization_id} after marketplace install")

        return InstallServerResponse(
            success=True,
            message=f"Server {request.server_id} installed successfully",
            server_id=server.server_id,
            server_uuid=str(server.id)
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error installing server {request.server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_servers(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=50, description="Maximum results"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    Quick search for MCP servers.

    Searches in server name, description, and tags.
    Returns top results sorted by relevance (popularity).
    """
    try:
        result = await marketplace.list_servers(
            search=q,
            limit=limit
        )

        return {
            "query": q,
            "results": result["servers"],
            "total": result["total"]
        }

    except Exception as e:
        logger.error(f"Error searching marketplace: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/featured")
async def get_featured_servers(
    limit: int = Query(10, ge=1, le=20, description="Number of featured servers"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace)
):
    """
    Get featured/popular MCP servers.

    Returns verified and high-popularity servers for homepage display.
    """
    try:
        result = await marketplace.list_servers(
            verified_only=True,
            limit=limit
        )

        # If not enough verified, add popular unverified
        if len(result["servers"]) < limit:
            additional = await marketplace.list_servers(
                limit=limit - len(result["servers"])
            )
            # Add servers not already in list
            existing_ids = {s["id"] for s in result["servers"]}
            for server in additional["servers"]:
                if server["id"] not in existing_ids:
                    result["servers"].append(server)
                    if len(result["servers"]) >= limit:
                        break

        return {
            "featured": result["servers"][:limit]
        }

    except Exception as e:
        logger.error(f"Error getting featured servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/team-servers")
async def list_team_servers(
    request: Request,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    marketplace: MarketplaceSyncService = Depends(get_marketplace),
    db=Depends(get_db)
):
    """
    List marketplace servers that have organization credentials configured.

    Returns servers where the user's organization has pre-configured credentials,
    allowing members to connect with team-shared credentials.

    Response includes:
    - marketplace_server: Full marketplace server data
    - org_credential: Organization credential details (credentials masked)
    - is_fully_configured: True if all required credentials are provided
    """
    user, _ = auth

    try:
        # Get user's organization
        if not user.organization_memberships:
            return []

        # Get org_id from JWT token (if present) to respect organization context
        from ...services.auth_service import AuthService
        token_org_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            payload = AuthService.decode_token(token)
            if payload:
                token_org_id = payload.get("org_id")

        # Find the right membership based on org_id from token
        membership = None
        if token_org_id:
            for m in user.organization_memberships:
                if str(m.organization_id) == token_org_id:
                    membership = m
                    break

        # Fallback to first membership if no token org_id (only for single-org users)
        if not membership:
            if len(user.organization_memberships) == 1:
                membership = user.organization_memberships[0]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Organization context required for multi-org users"
                )

        organization_id = membership.organization_id

        # Get all org credentials for this organization
        from ...services.credential_service import CredentialService
        from ...models.user_credential import OrganizationCredential
        from ...models.organization import UserRole
        from sqlalchemy import select

        credential_service = CredentialService(db)

        # Get user's role to determine visibility filtering
        is_admin = membership.role in [UserRole.ADMIN, UserRole.OWNER]

        # Fetch org credentials
        org_credentials = await credential_service.get_org_credentials(
            organization_id=organization_id,
            include_inactive=False
        )

        # Filter for non-admins: only visible_to_users=True
        if not is_admin:
            org_credentials = [c for c in org_credentials if c.visible_to_users]

        # For each org credential, fetch corresponding marketplace server
        team_servers = []
        for org_cred in org_credentials:
            # Get marketplace server ID from server relationship
            # org_cred.server has the MCPServer, which has env._MARKETPLACE_SERVER_ID
            mcp_server = org_cred.server

            if not mcp_server or not mcp_server.env:
                continue

            marketplace_server_id = mcp_server.env.get("_MARKETPLACE_SERVER_ID")

            if not marketplace_server_id:
                # Fallback to server_id if no marketplace ID stored
                marketplace_server_id = mcp_server.server_id

            # Fetch marketplace server data
            try:
                marketplace_server = await marketplace.get_server(marketplace_server_id)

                if not marketplace_server:
                    continue

                # Determine if fully configured (all required credentials present)
                required_creds = [
                    cred for cred in marketplace_server.get("credentials", [])
                    if cred.get("required", False)
                ]

                # Get org credential keys
                org_cred_keys = set(org_cred.credentials.keys()) if org_cred.credentials else set()

                required_keys = {cred.get("name") for cred in required_creds}
                is_fully_configured = required_keys.issubset(org_cred_keys)

                team_servers.append({
                    "marketplace_server": marketplace_server,
                    "org_credential": {
                        "id": str(org_cred.id),
                        "server_id": str(org_cred.server_id),
                        "name": org_cred.name,
                        "description": org_cred.description,
                        "visible_to_users": org_cred.visible_to_users,
                        "is_active": org_cred.is_active,
                        "created_at": org_cred.created_at.isoformat() if org_cred.created_at else None,
                        "credential_keys": list(org_cred_keys)  # Just the keys, not values
                    },
                    "is_fully_configured": is_fully_configured
                })
            except Exception as e:
                logger.warning(f"Failed to fetch marketplace server {marketplace_server_id}: {e}")
                continue

        return team_servers

    except Exception as e:
        logger.error(f"Error listing team servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect", response_model=ConnectServerResponse)
async def connect_server(
    request: ConnectServerRequest,
    auth: tuple[User, Optional[APIKey]] = Depends(get_current_user),
    marketplace: MarketplaceSyncService = Depends(get_marketplace),
    db=Depends(get_db)
):
    """
    Connect to a marketplace server (install + configure credentials in one operation).

    This endpoint combines server installation and credential configuration into
    a single atomic operation. It always creates a NEW server instance, allowing
    users to install the same MCP server multiple times with different credentials
    (e.g., Grist Personal, Grist Work).

    Required:
    - server_id: Marketplace server ID (e.g., 'grist-mcp')
    - organization_id: Organization to install to
    - credentials: Credential dictionary for the server
    - name: Name to distinguish this instance (e.g., "Grist Personal")

    Flow:
    1. Get server template from marketplace
    2. Install NEW server instance to organization
    3. Create user credentials for this specific instance
    4. Return complete connection details
    """
    user, _ = auth
    try:

        # Get server data from marketplace
        server_data = await marketplace.get_server(request.server_id)

        if not server_data:
            raise HTTPException(
                status_code=404,
                detail=f"Server not found in marketplace: {request.server_id}"
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

        # Determine default command based on install type
        default_command = "uvx" if install_type == InstallType.PIP else "npx"

        # Generate unique server name and instance ID
        # User provides a name like "GitHub Personal" which becomes both display name and unique ID
        base_server_id = request.server_id  # Original marketplace ID (e.g., "github")
        server_name = request.name or server_data.get('name', request.server_id)

        # DEBUG: Log what we received
        logger.warning(f"🔍 Connect Debug - request.name: '{request.name}', server_name: '{server_name}', base_server_id: '{base_server_id}'")

        # Generate unique instance_id from user-provided name
        # This allows multiple instances of the same service per organization
        # Examples:
        #   "GitHub Personal" + "github" → "github-personal"
        #   "Work Account" + "github" → "github-work-account"
        #   "GitHub" + "github" → "github-2" (unique suffix added)
        import re
        from datetime import datetime
        name_slug = re.sub(r'[^a-z0-9]+', '-', server_name.lower()).strip('-')

        if request.name:
            # If name already starts with base_server_id, extract the suffix
            if name_slug.startswith(base_server_id):
                # Check if there's actually a suffix after base_server_id
                suffix = name_slug[len(base_server_id):].lstrip('-')
                if suffix:
                    # "GitHub Personal" → "github-personal"
                    instance_server_id = f"{base_server_id}-{suffix}"
                else:
                    # "GitHub" → need unique suffix, use timestamp
                    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                    instance_server_id = f"{base_server_id}-{timestamp}"
            else:
                # "Work Account" → "github-work-account"
                instance_server_id = f"{base_server_id}-{name_slug}"
        else:
            instance_server_id = base_server_id

        # DEBUG: Log the generated instance_server_id
        logger.warning(f"🔍 Connect Debug - name_slug: '{name_slug}', instance_server_id: '{instance_server_id}'")

        mcp_service = MCPServerService(db)
        credential_service = CredentialService(db)

        # For team services (use_org_credentials=True), we use the existing TEAM server
        # (the one with org credentials), not personal servers
        if request.use_org_credentials:
            logger.info(f"Using organization credentials for {server_name}")

            from sqlalchemy import select, text
            from ...models.user_credential import OrganizationCredential
            from ...models.mcp_server import MCPServer

            # Find the TEAM server - must have org credentials for this marketplace ID
            # This ensures we don't accidentally use a personal server
            result = await db.execute(
                select(MCPServer)
                .join(OrganizationCredential, OrganizationCredential.server_id == MCPServer.id)
                .where(MCPServer.organization_id == request.organization_id)
                .where(OrganizationCredential.organization_id == request.organization_id)
                .where(text("mcp_servers.env @> :marketplace_id"))
                .params(marketplace_id=f'{{"_MARKETPLACE_SERVER_ID": "{base_server_id}"}}')
                .limit(1)
            )
            existing_server = result.scalar_one_or_none()

            if not existing_server:
                raise HTTPException(
                    status_code=404,
                    detail=f"No team server found for {request.server_id}. Admin must first configure the Team Service."
                )

            # Get the org credential for this server
            org_cred = await credential_service._get_org_credential(
                organization_id=request.organization_id,
                server_id=existing_server.id
            )

            if not org_cred:
                raise HTTPException(
                    status_code=404,
                    detail=f"No organization credentials found for {request.server_id}"
                )

            # Use the existing server's UUID
            server_uuid = existing_server.id
            server_name = existing_server.name

            # Merge org credentials with additional credentials from user
            final_credentials = dict(org_cred.credentials) if org_cred.credentials else {}
            if request.additional_credentials:
                final_credentials.update(request.additional_credentials)
                logger.info(f"Merged {len(request.additional_credentials)} additional credentials for Team service")

            # Create or update user credential linked to the existing team server
            # User might already have credentials from a previous connection attempt
            # or from before this server was configured as a team service
            existing_user_cred = await credential_service._get_user_credential(user.id, server_uuid)

            if existing_user_cred:
                # Update existing credentials with merged values
                logger.info(f"Updating existing user credentials for team server {server_uuid}")
                credential = await credential_service.update_user_credential(
                    user_id=user.id,
                    server_id=server_uuid,
                    credentials=final_credentials,
                    name=server_name
                )
            else:
                # Create new user credentials
                try:
                    credential = await credential_service.create_user_credential(
                        user_id=user.id,
                        server_id=server_uuid,
                        organization_id=request.organization_id,
                        credentials=final_credentials,
                        name=server_name
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))

        else:
            # Normal flow: Create new server instance
            # Build env: copy fixed values from source server + add marketplace ID
            source_env = server_data.get("env", {})
            server_env = {"_MARKETPLACE_SERVER_ID": base_server_id}
            for key, value in source_env.items():
                # Copy fixed values (not placeholders like ${VAR})
                if isinstance(value, str) and not value.startswith("${"):
                    server_env[key] = value

            logger.info(f"🔧 Server env from source: {source_env}")
            logger.info(f"🔧 Server env to create: {server_env}")

            server = await mcp_service.create_server(
                organization_id=request.organization_id,
                server_id=instance_server_id,
                name=server_name,
                install_type=install_type,
                install_package=server_data.get("install_package", ""),
                command=server_data.get("command", default_command),
                args=server_data.get("args", []),
                env=server_env,
                version=server_data.get("version"),
                auto_start=False
            )

            server_uuid = server.id

            # Use provided credentials directly
            final_credentials = request.credentials

            # Create user credential
            try:
                credential = await credential_service.create_user_credential(
                    user_id=user.id,
                    server_id=server_uuid,
                    organization_id=request.organization_id,
                    credentials=final_credentials,
                    name=server_name
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Step 3: Install and start server with user's credentials if auto_start requested
        # This applies to both team services and normal flow
        if request.auto_start:
            logger.info(f"Auto-starting server {server_name} with user credentials")
            try:
                # Install the package (pip/npm) first - required since auto_start=False in create_server
                await mcp_service.install(server_uuid)
                # Now start with user credentials
                await mcp_service.start(
                    server_id=server_uuid,
                    user_id=user.id,
                    organization_id=request.organization_id
                )
                logger.info(f"Server {server_name} started successfully")
            except Exception as start_error:
                logger.error(f"Failed to auto-start server {server_name}: {start_error}")
                # Don't fail the whole connection if start fails
                # User can manually start from dashboard

        # Invalidate user tool cache since a new server was connected
        from ...services.user_tool_cache import get_user_tool_cache
        tool_cache = get_user_tool_cache()
        await tool_cache.invalidate(user.id)
        logger.info(f"Invalidated tool cache for user {user.id} after server connection")

        return ConnectServerResponse(
            success=True,
            message=f"Server '{server_name}' connected successfully",
            server_id=request.server_id,
            server_uuid=str(server_uuid),
            credential_id=str(credential.id),
            already_installed=request.use_org_credentials  # Team services reuse existing server
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error connecting to server {request.server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LLM Curation Endpoints
# ============================================================================

class CurationStatusResponse(BaseModel):
    """Response model for curation status."""
    total_servers: int
    curated_servers: int
    pending_curation: int
    needs_icon_refresh: int = 0
    llm_configured: bool
    cache_path: Optional[str] = None


class CurationResultResponse(BaseModel):
    """Response model for curation result."""
    status: str
    message: Optional[str] = None
    total_curated: int
    new_curated: int
    remaining: Optional[int] = None
    errors: Optional[list] = None


@router.get("/curation/status", response_model=CurationStatusResponse)
async def get_curation_status(
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Get LLM curation status.

    **Requires: Instance Admin privileges**

    Shows how many servers have been analyzed by LLM and how many are pending.
    """
    try:
        status = await marketplace.get_curation_status()
        return CurationStatusResponse(**status)
    except Exception as e:
        logger.error(f"Error getting curation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/curation/run", response_model=CurationResultResponse)
async def run_curation(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(5, ge=1, le=20, description="Servers per LLM batch"),
    max_servers: int = Query(50, ge=1, le=200, description="Max servers to curate"),
    semantic_dedup: bool = Query(False, description="Also run semantic deduplication (slower but more accurate)"),
    admin_user: User = Depends(require_instance_admin),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Run LLM curation on new servers.

    **Requires: Instance Admin privileges**

    Only analyzes servers not already in the curated cache.

    Args:
        batch_size: Number of servers to process per LLM API call
        max_servers: Maximum number of new servers to curate in this run
        semantic_dedup: If True, also run semantic deduplication using vector similarity + LLM
    """

    try:
        result = await marketplace.curate_new_servers(
            batch_size=batch_size,
            max_servers=max_servers,
            semantic_dedup=semantic_dedup
        )
        return CurationResultResponse(**result)
    except Exception as e:
        logger.error(f"Error running curation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/curation/run-background")
async def run_curation_background(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(5, ge=1, le=20),
    max_servers: int = Query(100, ge=1, le=500),
    admin_user: User = Depends(require_instance_admin),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Run LLM curation in background.

    **Requires: Instance Admin privileges**

    Returns immediately while curation runs asynchronously.
    Use /curation/status to check progress.
    """

    async def run_background_curation():
        try:
            await marketplace.curate_new_servers(
                batch_size=batch_size,
                max_servers=max_servers
            )
            logger.info("Background curation completed")
        except Exception as e:
            logger.error(f"Background curation error: {e}")

    background_tasks.add_task(run_background_curation)

    return {
        "status": "started",
        "message": "Curation started in background",
        "batch_size": batch_size,
        "max_servers": max_servers
    }


class FullCurationResultResponse(BaseModel):
    """Response model for full curation result."""
    status: str
    cache_cleared: Optional[int] = None
    total_curated: int
    new_curated: int
    remaining: Optional[int] = None
    errors: Optional[list] = None
    deduplication: Optional[dict] = None


@router.post("/curation/force-full", response_model=FullCurationResultResponse)
async def force_full_curation(
    batch_size: int = Query(5, ge=1, le=20, description="Servers per LLM batch"),
    max_servers: int = Query(200, ge=1, le=500, description="Max servers to curate"),
    admin_user: User = Depends(require_instance_admin),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Force FULL re-curation of ALL servers.

    **Requires: Instance Admin privileges**

    WARNING: This clears the curation cache and re-analyzes ALL servers with LLM.
    Use this after major prompt updates to refresh all curation data.

    This will:
    1. Clear the existing curation cache
    2. Re-curate all servers with the updated LLM prompt
    3. Run deduplication after curation
    """

    try:
        result = await marketplace.force_full_curation(
            batch_size=batch_size,
            max_servers=max_servers
        )
        return FullCurationResultResponse(**result)
    except Exception as e:
        logger.error(f"Error in force full curation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class IconRefreshResponse(BaseModel):
    """Response model for icon refresh operations."""
    status: str
    message: Optional[str] = None
    total_needing_refresh: Optional[int] = None
    total_checked: Optional[int] = None
    processed: Optional[int] = None
    refreshed: Optional[int] = None
    newly_validated: Optional[int] = None
    still_invalid: Optional[int] = None
    failed: Optional[int] = None
    failed_details: Optional[list] = None
    remaining: Optional[int] = None


@router.post("/curation/refresh-icons", response_model=IconRefreshResponse)
async def refresh_invalid_icons(
    max_servers: int = Query(100, ge=1, le=500, description="Max servers to process"),
    admin_user: User = Depends(require_instance_admin),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Re-curate ONLY servers with invalid/unvalidated icons.

    **Requires: Instance Admin privileges**

    Uses LLM to get new icon_search_terms for servers without validated icons.
    Does NOT modify other curation data - only updates icon fields.

    This is useful when:
    - Icon CDN URLs have changed
    - Previous curation had incorrect icon_hint values
    - You want to improve icon coverage without full re-curation
    """

    try:
        result = await marketplace.refresh_invalid_icons(max_servers=max_servers)
        return IconRefreshResponse(**result)
    except Exception as e:
        logger.error(f"Error refreshing icons: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/curation/revalidate-icons", response_model=IconRefreshResponse)
async def revalidate_existing_icons(
    max_servers: int = Query(200, ge=1, le=1000, description="Max servers to check"),
    admin_user: User = Depends(require_instance_admin),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Re-validate existing icon_search_terms without calling LLM.

    **Requires: Instance Admin privileges**

    For servers that have icon_search_terms but not icon_validated,
    this just re-tests the terms against CDNs without re-curating.

    This is MUCH FASTER than refresh-icons because it doesn't call the LLM.
    Use this when you just want to re-test existing search terms.

    Example use case:
    - After clearing the IconResolver validation cache
    - To check if previously invalid slugs now work
    """

    try:
        result = await marketplace.revalidate_existing_icons(max_servers=max_servers)
        return IconRefreshResponse(**result)
    except Exception as e:
        logger.error(f"Error revalidating icons: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/curation/validate-icons")
async def validate_icons(
    force: bool = Query(False, description="Force re-sync even if cache is valid"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Validate and resolve icons for all marketplace servers.

    **Requires: Instance Admin privileges**

    This triggers a sync that resolves icons for all servers and then
    persists the result to marketplace_registry.json.

    Icons are resolved using:
    - iconHint from curation data
    - Service name matching against SimpleIcons
    - LobeHub icon CDN as fallback

    Note: bigmcp_source.json is READ-ONLY. Results are saved to
    marketplace_registry.json which can be edited.

    Use force=true to force re-sync, otherwise uses cache if valid.
    """
    try:
        # Sync (which includes icon resolution) and persist
        result = await marketplace.sync_and_persist(force=force, persist=True)

        # Extract icon stats from servers
        servers_with_icons = sum(
            1 for s in marketplace._servers.values()
            if s.icon_url
        )

        return {
            "status": "success",
            "icons_resolved": servers_with_icons,
            "total_servers": len(marketplace._servers),
            "persisted_to": result["persistence"].get("registry_path"),
            "sync_status": result["sync"].get("status")
        }
    except Exception as e:
        logger.error(f"Error validating icons: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SemanticDeduplicationResponse(BaseModel):
    """Response model for semantic deduplication."""
    status: str
    servers_analyzed: int
    potential_duplicates_found: int
    confirmed_duplicate_groups: int
    servers_marked_duplicate: int
    similarity_threshold: float
    llm_confirmed: bool
    groups: list = []


@router.post("/curation/semantic-deduplicate", response_model=SemanticDeduplicationResponse)
async def semantic_deduplicate(
    similarity_threshold: float = Query(0.80, ge=0.5, le=1.0, description="Minimum similarity score to consider duplicates"),
    confirm_with_llm: bool = Query(True, description="Use LLM to confirm duplicates (recommended)"),
    dry_run: bool = Query(False, description="Only report duplicates without applying changes"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service),
    admin_user: User = Depends(require_instance_admin)
):
    """
    Semantically deduplicate servers using AI.

    **Requires: Instance Admin privileges**

    This endpoint uses a two-phase approach:
    1. **Vector Similarity**: Finds potentially similar servers using embeddings
    2. **LLM Confirmation**: Uses AI to confirm if servers are true duplicates

    Unlike regex-based deduplication (_get_dedup_key), this approach:
    - Handles any naming convention correctly
    - Identifies the underlying service (service_id) regardless of package name
    - Detects duplicates like "@winor30/mcp-server-datadog" and "datadog-mcp-server"
    - Selects the best variant (prefers official/verified sources)

    Use dry_run=true to preview which duplicates would be detected without changes.
    """
    try:
        result = await marketplace.semantic_deduplicate(
            similarity_threshold=similarity_threshold,
            confirm_with_llm=confirm_with_llm,
            dry_run=dry_run
        )
        return SemanticDeduplicationResponse(**result)
    except Exception as e:
        logger.error(f"Error in semantic deduplication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servers/{server_id}/similar")
async def find_similar_servers(
    server_id: str,
    threshold: float = Query(0.75, ge=0.5, le=1.0, description="Minimum similarity score"),
    marketplace: MarketplaceSyncService = Depends(get_marketplace_service)
):
    """
    Find servers semantically similar to the given server.

    Uses vector embeddings to find servers with similar descriptions/purposes.
    Useful for:
    - Detecting potential duplicates
    - Finding alternative implementations of the same service
    - Discovering related servers
    """
    try:
        # Get the server first
        if not marketplace._servers:
            await marketplace.sync()

        server = marketplace._servers.get(server_id)
        if not server:
            raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

        similar = await marketplace.find_similar_servers(server, threshold=threshold)
        return {
            "server_id": server_id,
            "server_name": server.name,
            "threshold": threshold,
            "similar_servers": similar
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding similar servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
