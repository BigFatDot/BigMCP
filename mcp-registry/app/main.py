"""
Main entry point for the MCP Registry application.
"""

import logging
import uvicorn
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
import asyncio
import time

from .api import router as api_router
from .api.v1 import api_router as api_v1_router
from .api.v1.auth import router as auth_router
from .api.v1.api_keys import router as api_keys_router
from .api.v1.oauth import router as oauth_router
from .api.v1.marketplace_keys import router as marketplace_keys_router
from .api.v1.marketplace import router as marketplace_router
from .api.v1.organizations import router as organizations_router
from .api.v1.compositions import router as compositions_router
from .api.v1.admin import router as admin_router
from .api.v1.mfa import router as mfa_router
from .api.well_known import router as well_known_router

# Edition detection for conditional router registration
from .core.edition import get_edition, Edition
_current_edition = get_edition()
from .routers import mcp_unified
from .dependencies import get_registry
from .api.dependencies import get_current_user
from .config import settings

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp_registry")

# Create the FastAPI application
app = FastAPI(
    title=settings.app.name,
    description=settings.app.description,
    version=settings.app.version,
)

# Configure Jinja2 templates for OAuth consent page
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Set templates in OAuth router
from .api.v1 import oauth as oauth_module
oauth_module.templates = templates

# Add CORS middleware
# Production: Use configured origins from CORS_ORIGINS env var
# Development: Allow all origins when DEBUG=true
from .core.config import settings as core_settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if core_settings.DEBUG else core_settings.CORS_ORIGINS,
    allow_credentials=core_settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=core_settings.CORS_ALLOW_METHODS,
    allow_headers=core_settings.CORS_ALLOW_HEADERS,
)

# Add security headers middleware (HSTS, CSP, X-Frame-Options, etc.)
from .middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware, debug=core_settings.DEBUG)

# Add rate limiting middleware for all API endpoints
# Configuration loaded from settings.RATE_LIMIT_ROUTES
from .middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Add Prometheus metrics middleware for observability
# Records HTTP request count and latency for /metrics endpoint
from .middleware.prometheus import PrometheusMiddleware
app.add_middleware(PrometheusMiddleware)

# Middleware to handle .well-known routes
# FastAPI/Starlette has issues with routes starting with a dot
@app.middleware("http")
async def handle_well_known_middleware(request: Request, call_next):
    """
    Middleware to handle .well-known routes that FastAPI can't route properly.

    FastAPI/Starlette treats paths starting with '.' specially, causing routing issues.
    This middleware intercepts these requests and handles them directly.
    """
    from fastapi.responses import JSONResponse

    # Debug logging
    logger.info(f"Middleware: received path = {request.url.path}")

    if request.url.path == "/.well-known/oauth-authorization-server":
        # Detect correct scheme (http vs https) from X-Forwarded-Proto header
        # This is set by ngrok/nginx when proxying HTTPS requests
        scheme = request.headers.get("x-forwarded-proto", "http")
        host = request.headers.get("host", str(request.base_url.hostname))

        # Force https if request comes from ngrok (ngrok free doesn't send X-Forwarded-Proto)
        if "ngrok" in host:
            scheme = "https"

        base_url = f"{scheme}://{host}"

        logger.info(f"OAuth Discovery: scheme={scheme}, host={host}, base_url={base_url}")
        logger.info(f"OAuth Discovery: X-Forwarded-Proto={request.headers.get('x-forwarded-proto')}, Host={request.headers.get('host')}")

        return JSONResponse(content={
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
            "token_endpoint": f"{base_url}/api/v1/oauth/token",
            "registration_endpoint": f"{base_url}/api/v1/oauth/register",
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
                "none"
            ],
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token"
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
            "scopes_supported": [
                "mcp:execute",
                "mcp:read",
                "mcp:write",
                "offline_access"  # Required for refresh tokens (RFC 6749)
            ],
            "service_documentation": f"{base_url}/docs",
            "ui_locales_supported": ["en-US", "fr-FR"],
            "registration_endpoint_supported": True
        })

    elif request.url.path == "/.well-known/oauth-protected-resource":
        # Detect correct scheme (http vs https) from X-Forwarded-Proto header
        scheme = request.headers.get("x-forwarded-proto", "http")
        host = request.headers.get("host", str(request.base_url.hostname))

        # Force https if request comes from ngrok (ngrok free doesn't send X-Forwarded-Proto)
        if "ngrok" in host:
            scheme = "https"

        base_url = f"{scheme}://{host}"

        return JSONResponse(content={
            "resource": base_url,
            "authorization_servers": [base_url],
            "scopes_supported": [
                "mcp:execute",
                "mcp:read",
                "mcp:write",
                "offline_access"  # Required for refresh tokens (RFC 6749)
            ],
            "bearer_methods_supported": ["header", "query"],
            "resource_documentation": f"{base_url}/docs",
            "mcp_endpoints": {
                "sse": f"{base_url}/mcp/sse",
                "message": f"{base_url}/mcp/message",
                "health": f"{base_url}/mcp/health",
                "tools": f"{base_url}/mcp/tools"
            },
            "mcp_protocol_version": "2025-03-26",
            "capabilities": [
                "Tool aggregation from multiple MCP servers",
                "Intelligent orchestration via LLM API",
                "Semantic tool search",
                "Workflow composition",
                "Credential management"
            ]
        })

    response = await call_next(request)
    return response


# Direct endpoint to bypass uvicorn blocking of .well-known paths
# Uvicorn blocks paths starting with '.' before they reach middleware
@app.get("/.well-known/oauth-authorization-server", include_in_schema=False)
async def oauth_discovery_direct(request: Request):
    """OAuth 2.0 Authorization Server Metadata (RFC 8414) - Direct endpoint."""
    logger.info(f"Direct endpoint: /.well-known/oauth-authorization-server accessed")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    base_url = f"{scheme}://{host}"

    return JSONResponse(content={
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/api/v1/oauth/authorize",
        "token_endpoint": f"{base_url}/api/v1/oauth/token",
        "registration_endpoint": f"{base_url}/api/v1/oauth/register",
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "none"
        ],
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "refresh_token"
        ],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": [
            "mcp:execute",
            "mcp:read",
            "mcp:write",
            "offline_access"  # Required for refresh tokens (RFC 6749)
        ],
        "service_documentation": f"{base_url}/docs",
        "ui_locales_supported": ["en-US", "fr-FR"],
        "registration_endpoint_supported": True
    })


# Include routers
# OAuth Discovery endpoints (.well-known) - must be at root level
app.include_router(well_known_router, tags=["OAuth Discovery"])

# Unified MCP Gateway router (main priority)
app.include_router(mcp_unified.router, tags=["MCP Gateway - Unified"])

# ============================================================================
# Core Routes - Available on ALL editions
# ============================================================================
app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(api_keys_router, prefix="/api/v1", tags=["API Keys"])
app.include_router(oauth_router, prefix="/api/v1", tags=["OAuth 2.0"])
app.include_router(marketplace_keys_router, prefix="/api/v1", tags=["Marketplace Keys"])
app.include_router(marketplace_router, prefix="/api/v1", tags=["Marketplace"])
app.include_router(organizations_router, prefix="/api/v1", tags=["Organizations"])
app.include_router(compositions_router, prefix="/api/v1", tags=["Compositions"])
app.include_router(admin_router, prefix="/api/v1", tags=["Instance Admin"])
app.include_router(mfa_router, prefix="/api/v1", tags=["MFA"])

# ============================================================================
# Cloud SaaS Routes - Only available on bigmcp.cloud
# ============================================================================
# These routes are only registered when running as Cloud SaaS edition.
# On Community/Enterprise, these endpoints return 404 (not found).
if _current_edition == Edition.CLOUD_SAAS:
    from .api.v1.webhooks import router as webhooks_router
    from .api.v1.subscriptions import router as subscriptions_router
    from .api.v1.licenses import router as licenses_router
    from .api.v1.enterprise import router as enterprise_router

    app.include_router(webhooks_router, prefix="/api/v1", tags=["Webhooks"])
    app.include_router(subscriptions_router, prefix="/api/v1", tags=["Subscriptions"])
    app.include_router(licenses_router, prefix="/api/v1", tags=["Licenses"])
    app.include_router(enterprise_router, prefix="/api/v1", tags=["Enterprise"])

    logging.getLogger("mcp_registry").info("Cloud SaaS edition: billing routes enabled")

# API v1 router (Dynamic MCP server management, contexts, bindings)
app.include_router(api_v1_router, tags=["API v1"])

# Legacy API router
app.include_router(api_router, tags=["API"])

@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting MCP Registry...")

    # Security warnings for DEBUG mode
    if core_settings.DEBUG:
        logger.warning("⚠️  DEBUG mode enabled - NOT FOR PRODUCTION USE")
        if hasattr(core_settings, '_secret_key_auto_generated') and core_settings._secret_key_auto_generated:
            logger.warning("⚠️  SECRET_KEY auto-generated - JWT tokens will be invalidated on restart")
        logger.warning("⚠️  CORS allows all origins in DEBUG mode")

    # Detect and log edition
    from .core.edition import get_edition, get_license_org_name, Edition
    edition = get_edition()
    if edition == Edition.CLOUD_SAAS:
        logger.info("🚀 Edition: CLOUD_SAAS (bigmcp.cloud)")
    elif edition == Edition.ENTERPRISE:
        org_name = get_license_org_name() or "Unknown"
        logger.info(f"🏢 Edition: ENTERPRISE (org: {org_name})")
    else:
        logger.info("🏠 Edition: COMMUNITY (1 user limit)")

    # Initialize Prometheus metrics
    from .core.metrics import init_app_info
    init_app_info(version=settings.app.version, edition=edition.value)

    # Initialize database (create tables if they don't exist)
    from .db.database import init_db, get_async_session
    await init_db()

    # Initialize token blacklist from database
    from .services.token_blacklist_service import TokenBlacklistService
    async for db in get_async_session():
        await TokenBlacklistService.initialize(db)
        break
    logger.info("Token blacklist initialized")

    # Seed public sector whitelist (Cloud SaaS only)
    if edition == Edition.CLOUD_SAAS:
        from .services.public_sector_service import PublicSectorService
        async for db in get_async_session():
            service = PublicSectorService(db)
            added = await service.seed_initial_whitelist()
            if added > 0:
                logger.info(f"Seeded {added} public sector domains")
            break

    # Initialize Redis + cache backend
    from .core.redis_client import init_redis
    from .core.cache_backend import init_cache_backend
    redis_client = await init_redis(core_settings.REDIS_URL) if core_settings.REDIS_URL else None
    init_cache_backend(redis_client=redis_client, prefix=core_settings.REDIS_PREFIX)

    # Load marketplace cache before starting services
    from .services.marketplace_service import get_marketplace_service
    marketplace_service = get_marketplace_service()
    await marketplace_service.load_from_cache_file()
    logger.info("Marketplace cache loading completed")

    # Get the shared registry instance
    registry = get_registry()

    # Start the discovery service
    await registry.start()

    # Start UserServerPool for per-user MCP server management
    from .routers.mcp_unified import gateway
    await gateway.user_server_pool.start()
    logger.info("UserServerPool started")

    logger.info("MCP Registry started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Stopping MCP Registry...")

    # Stop UserServerPool and cleanup all user servers
    from .routers.mcp_unified import gateway
    await gateway.user_server_pool.stop()
    logger.info("UserServerPool stopped")

    # Stop registry
    registry = get_registry()
    await registry.stop()

    # Close Redis connection
    from .core.redis_client import close_redis
    await close_redis()

    # Close database connections
    from .db.database import close_db
    await close_db()

    logger.info("MCP Registry stopped successfully")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler - masks details in production."""
    logger.exception(f"Unhandled exception: {exc}")

    # Only expose error details in DEBUG mode
    if core_settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )
    else:
        # Production: generic message, no internal details leaked
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

# MCP Proxy Routes - Forward MCP requests from / to /mcp/sse
# This allows Claude Desktop to use base URL while still connecting to /mcp/sse

@app.get("/")
async def root_get(request: Request):
    """
    Root GET endpoint - MCP proxy or info page.

    If the request has MCP headers (mcp-protocol-version or Accept: text/event-stream),
    forward to /mcp/sse with proper authentication. Otherwise, return service info.

    Per MCP 2025-03-26 spec: GET / with Accept: text/event-stream opens a server→client
    SSE notification channel. Returns 401 if unauthenticated, 405 if wrong format.
    """
    # Check if this is an MCP SSE request
    mcp_version = request.headers.get("mcp-protocol-version")
    accept = request.headers.get("accept", "")

    if mcp_version or "text/event-stream" in accept:
        # MCP SSE request — must authenticate before proxying.
        # FastAPI DI (Depends) is NOT injected when calling endpoint functions
        # directly; we must resolve auth manually from the request.
        authorization = request.headers.get("authorization")
        if not authorization:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            scheme, key = authorization.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format. Expected: Bearer <api_key>"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Resolve auth against the database (mirrors get_current_user_api_key logic)
        from .db.database import get_async_session
        from .services.auth_service import AuthService

        auth = None
        async for db in get_async_session():
            auth_service = AuthService(db)
            auth = await auth_service.validate_api_key(key)
            break

        if not auth:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info(f"🔄 Proxying GET / → GET /mcp/sse (MCP request detected, user: {auth[1].email})")
        from .routers.mcp_unified import mcp_sse_endpoint
        return await mcp_sse_endpoint(request, auth)

    # Regular web request - return info
    return {
        "name": "MCPHub Gateway",
        "version": "1.0.0",
        "description": "Unified MCP Gateway with intelligent orchestration",
        "documentation": "/docs",
        "endpoints": {
            "primary": "/mcp/sse (Server-Sent Events)",
            "message_handler": "/mcp/message (JSON-RPC 2.0)",
            "health": "/health",
            "api_docs": "/docs"
        },
        "features": [
            "Tool aggregation from multiple MCP servers",
            "Intelligent orchestration via LLM API",
            "Semantic tool search",
            "Workflow composition",
            "MCP Protocol 2025-03-26 compliant (Streamable HTTP)"
        ]
    }


@app.post("/")
async def root_post(request: Request, auth: tuple = Depends(get_current_user)):
    """
    Root POST endpoint - MCP proxy with authentication.

    If the request has MCP headers (mcp-protocol-version or JSON-RPC content),
    forward to /mcp/message logic. Otherwise, return 405 Method Not Allowed.

    Requires: Valid authentication (JWT or MCPHub API Key)
    """
    # Check if this is an MCP request
    mcp_version = request.headers.get("mcp-protocol-version")
    content_type = request.headers.get("content-type", "")

    if mcp_version or "application/json" in content_type:
        # This is an MCP request - use the internal handler with auth
        logger.info(f"🔄 Proxying POST / → POST /mcp/message (MCP request detected)")
        from .routers.mcp_unified import handle_mcp_message
        return await handle_mcp_message(request, auth)

    # Not an MCP request
    raise HTTPException(
        status_code=405,
        detail="Method Not Allowed - This endpoint only accepts MCP protocol requests"
    )


@app.delete("/")
async def root_delete(request: Request, auth: tuple = Depends(get_current_user)):
    """
    Session termination endpoint — MCP 2025-03-26 Streamable HTTP spec.

    Client sends DELETE / with Mcp-Session-Id header to explicitly close
    a session. Server cleans up session state and returns 200.

    Requires: Valid authentication (JWT or MCPHub API Key)
    """
    session_id = request.headers.get("mcp-session-id")
    if not session_id:
        return Response(status_code=400)

    from .routers.mcp_unified import mcp_sessions
    if session_id in mcp_sessions:
        del mcp_sessions[session_id]
        logger.info(f"MCP session {session_id} terminated by client")
        return Response(status_code=200)

    # Session not found — may have already expired; still a valid outcome
    return Response(status_code=404)


# Health check route
@app.get("/health")
async def health():
    """
    Check the service health status.
    """
    registry = get_registry()
    return {
        "status": "healthy",
        "servers_count": len(registry.servers),
        "tools_count": len(registry.tools)
    }

# MCP health check route
@app.get("/mcp/health")
async def mcp_health():
    """
    Health endpoint for the MCP protocol.
    """
    registry = get_registry()
    return {
        "status": "healthy",
        "protocol": "MCP",
        "version": "2025-03-26",
        "servers_count": len(registry.servers),
        "tools_count": len(registry.tools)
    }

# Readiness probe - verifies all dependencies are ready
@app.get("/ready")
async def readiness_probe():
    """
    Kubernetes-style readiness probe.

    Unlike /health (liveness), this checks if the service is ready
    to accept traffic by verifying all dependencies:
    - Database connection
    - Registry loaded
    - Cache backend available

    Returns 503 if not ready, 200 if ready.
    """
    from sqlalchemy import text

    checks = {
        "database": False,
        "registry": False,
        "cache": False,
    }

    # Check database connection
    try:
        from .db.database import get_async_session
        async for db in get_async_session():
            await db.execute(text("SELECT 1"))
            checks["database"] = True
            break
    except Exception as e:
        logger.warning(f"Readiness check: database not ready - {e}")

    # Check registry is loaded
    try:
        registry = get_registry()
        checks["registry"] = len(registry.servers) > 0 or len(registry.tools) > 0
    except Exception as e:
        logger.warning(f"Readiness check: registry not ready - {e}")

    # Check cache backend
    try:
        from .core.cache_backend import get_cache_backend
        backend = get_cache_backend()
        stats = await backend.get_stats()
        checks["cache"] = stats.get("backend") is not None
    except Exception as e:
        logger.warning(f"Readiness check: cache not ready - {e}")

    # Determine overall readiness (database and registry are required)
    is_ready = checks["database"] and checks["registry"]

    if not is_ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": checks,
            }
        )

    return {
        "status": "ready",
        "checks": checks,
    }


# Prometheus metrics endpoint
@app.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping.
    No authentication required (standard for metrics endpoints).

    Metrics exposed:
    - bigmcp_pool_*: Server pool statistics
    - bigmcp_cache_*: Cache statistics
    - bigmcp_sse_sessions_active: Active SSE connections
    - bigmcp_http_*: HTTP request metrics (from middleware)
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    from .core.metrics import collect_metrics

    # Collect current state metrics before generating output
    await collect_metrics()

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Edition status endpoint
@app.get("/edition/status")
async def edition_status():
    """
    Get current BigMCP edition information.

    Returns edition type, limits, and available features.
    Useful for frontend feature gating and diagnostics.
    """
    from .core.edition import (
        get_edition,
        get_license_org_name,
        get_license_features,
        get_max_users,
        get_max_organizations,
        is_saas,
        Edition
    )

    edition = get_edition()

    response = {
        "edition": edition.value,
        "limits": {
            "max_users": get_max_users(),
            "max_organizations": get_max_organizations(),
        },
        "features": {
            "billing": is_saas(),
            "sso": edition != Edition.COMMUNITY,
            "unlimited_users": edition != Edition.COMMUNITY,
            "organizations": edition != Edition.COMMUNITY,
        }
    }

    # Add license info for Enterprise
    if edition == Edition.ENTERPRISE:
        response["license"] = {
            "organization": get_license_org_name(),
            "features": get_license_features(),
        }

    # Add SaaS info
    if edition == Edition.CLOUD_SAAS:
        response["saas"] = {
            "billing_enabled": True,
            "marketplace_enabled": True,
        }

    return response

# Pool & cache monitoring endpoint (admin only)
@app.get("/api/v1/admin/pool-stats")
async def pool_stats(auth: tuple = Depends(get_current_user)):
    """
    Get UserServerPool and cache statistics.

    Requires authenticated user. Returns pool limits, active servers,
    cache backend status, and SSE session count.
    """
    from .routers.mcp_unified import gateway, mcp_sessions
    from .core.cache_backend import get_cache_backend
    from .core.redis_client import get_redis

    pool = gateway.user_server_pool
    backend = get_cache_backend()
    redis = get_redis()

    cache_stats = await backend.get_stats()

    return {
        "pool": pool.get_pool_stats(),
        "cache": cache_stats,
        "redis_connected": redis is not None,
        "active_sse_sessions": len(mcp_sessions),
    }

if __name__ == "__main__":
    # Run the application with Uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=True,
    )
