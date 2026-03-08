"""
API v1 - Multi-tenant MCP orchestration endpoints.
"""

from fastapi import APIRouter

from .mcp_servers import router as mcp_servers_router
from .contexts import router as contexts_router
from .tool_bindings import router as tool_bindings_router
from .tool_groups import router as tool_groups_router
from .tools import router as tools_router
from .user_credentials import router as user_credentials_router
from .org_credentials import router as org_credentials_router
from .api_keys import router as api_keys_router
from .marketplace import router as marketplace_router
from .discovery import router as discovery_router
from .subscriptions import router as subscriptions_router
from .webhooks import router as webhooks_router
from .admin import router as admin_router
from .admin_registry import router as admin_registry_router


# Main API router for v1
api_router = APIRouter(prefix="/api/v1")

# Include sub-routers
api_router.include_router(
    mcp_servers_router,
    prefix="/mcp-servers",
    tags=["MCP Servers"]
)

api_router.include_router(
    contexts_router,
    prefix="/contexts",
    tags=["Contexts"]
)

api_router.include_router(
    tool_bindings_router,
    prefix="/tool-bindings",
    tags=["Tool Bindings"]
)

api_router.include_router(
    tool_groups_router
)

api_router.include_router(
    tools_router,
    tags=["Tools"]
)

api_router.include_router(
    user_credentials_router,
    prefix="/user-credentials",
    tags=["User Credentials"]
)

api_router.include_router(
    org_credentials_router,
    prefix="/org-credentials",
    tags=["Organization Credentials (Admin)"]
)

api_router.include_router(
    api_keys_router
)

api_router.include_router(
    marketplace_router,
    tags=["Marketplace"]
)

api_router.include_router(
    discovery_router,
    tags=["Discovery"]
)

api_router.include_router(
    subscriptions_router,
    tags=["Subscriptions"]
)

api_router.include_router(
    webhooks_router,
    tags=["Webhooks"]
)

api_router.include_router(
    admin_router,
    tags=["Instance Admin"]
)

api_router.include_router(
    admin_registry_router,
    tags=["Instance Admin - Registry"]
)


__all__ = ["api_router"]
