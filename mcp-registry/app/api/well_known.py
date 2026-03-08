"""
OAuth 2.0 Discovery Endpoints (.well-known)

Implements RFC 8414: OAuth 2.0 Authorization Server Metadata
and RFC 8705: OAuth 2.0 Resource Indicators

These endpoints allow OAuth clients like Claude Desktop to automatically
discover the OAuth configuration without manual setup (Dynamic Client Registration).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["OAuth Discovery"])


@router.get("/well-known-test/oauth-authorization-server")
async def oauth_authorization_server_metadata_test(request: Request):
    """Test endpoint without leading dot."""
    base_url = str(request.base_url).rstrip('/')
    return JSONResponse(content={"test": "This endpoint works without the dot!", "base_url": base_url})


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata(request: Request):
    """
    OAuth 2.0 Authorization Server Metadata (RFC 8414).

    This endpoint allows OAuth clients like Claude Desktop to automatically
    discover the OAuth configuration without manual setup.

    Claude Desktop will:
    1. Fetch this endpoint
    2. Use the `registration_endpoint` to register itself (Dynamic Client Registration)
    3. Receive client_id and client_secret
    4. Use `authorization_endpoint` and `token_endpoint` for the OAuth flow
    """
    # Get the base URL from the request
    base_url = str(request.base_url).rstrip('/')

    return JSONResponse(content={
        "issuer": base_url,

        # Core OAuth endpoints
        "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
        "token_endpoint": f"{base_url}/api/v1/oauth/token",
        "registration_endpoint": f"{base_url}/api/v1/oauth/register",  # DCR endpoint

        # Supported authentication methods
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none"  # For public clients
        ],

        # Supported response types
        "response_types_supported": [
            "code"  # Authorization Code Flow
        ],

        # Supported grant types
        "grant_types_supported": [
            "authorization_code",
            "refresh_token"
        ],

        # PKCE support (RFC 7636)
        "code_challenge_methods_supported": [
            "S256",  # SHA-256 (recommended)
            "plain"  # Fallback
        ],

        # Supported scopes
        "scopes_supported": [
            "mcp:execute",     # Execute MCP tools
            "mcp:read",        # Read MCP metadata
            "mcp:write",       # Write/modify configurations
            "offline_access"   # Required for refresh tokens (RFC 6749)
        ],

        # Additional metadata
        "service_documentation": f"{base_url}/docs",
        "ui_locales_supported": [
            "en-US",
            "fr-FR"
        ],

        # Indicate we support Dynamic Client Registration
        "registration_endpoint_supported": True,

        # Token revocation (optional, for future implementation)
        # "revocation_endpoint": f"{base_url}/api/v1/oauth/revoke",
        # "revocation_endpoint_auth_methods_supported": ["client_secret_post"],

        # Introspection (optional, for future implementation)
        # "introspection_endpoint": f"{base_url}/api/v1/oauth/introspect",
        # "introspection_endpoint_auth_methods_supported": ["client_secret_post"]
    })


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_metadata(request: Request):
    """
    OAuth 2.0 Protected Resource Metadata (RFC 8705).

    Provides information about the protected resources (MCP endpoints)
    and how to access them.
    """
    base_url = str(request.base_url).rstrip('/')

    return JSONResponse(content={
        "resource": base_url,

        # Authorization servers that protect this resource
        "authorization_servers": [base_url],

        # Scopes required for this resource
        "scopes_supported": [
            "mcp:execute",
            "mcp:read",
            "mcp:write",
            "offline_access"   # Required for refresh tokens (RFC 6749)
        ],

        # Bearer token methods
        "bearer_methods_supported": [
            "header",  # Authorization: Bearer <token>
            "query"    # ?access_token=<token> (less recommended)
        ],

        # Resource documentation
        "resource_documentation": f"{base_url}/docs",

        # MCP-specific endpoints
        "mcp_endpoints": {
            "sse": f"{base_url}/mcp/sse",           # Server-Sent Events endpoint
            "message": f"{base_url}/mcp/message",   # JSON-RPC message handler
            "health": f"{base_url}/mcp/health",     # Health check
            "tools": f"{base_url}/mcp/tools"        # List available tools
        },

        # MCP Protocol version
        "mcp_protocol_version": "2024-11-05",

        # Capabilities
        "capabilities": [
            "Tool aggregation from multiple MCP servers",
            "Intelligent orchestration via LLM API",
            "Semantic tool search",
            "Workflow composition",
            "Credential management"
        ]
    })
