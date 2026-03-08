"""
Prometheus metrics for BigMCP.

Provides centralized metrics definitions and collection functions.
Exposes application metrics in Prometheus format via /metrics endpoint.

Metrics exposed:
- Pool gauges: active servers, users, vector stores
- Cache gauges: keys, hits, misses
- Session gauges: active SSE connections
- HTTP metrics: request count and latency (via middleware)

Usage:
    from app.core.metrics import collect_metrics, HTTP_REQUESTS, HTTP_DURATION

    # Collect current state metrics
    await collect_metrics()

    # Increment HTTP counter (done by middleware)
    HTTP_REQUESTS.labels(method="GET", endpoint="/api/v1/users", status="200").inc()
"""

import logging
from prometheus_client import Counter, Gauge, Histogram, Info

logger = logging.getLogger(__name__)

# =============================================================================
# Application Info
# =============================================================================

APP_INFO = Info(
    'bigmcp',
    'BigMCP application information'
)

# =============================================================================
# Pool Metrics (from UserServerPool.get_pool_stats())
# =============================================================================

POOL_SERVERS = Gauge(
    'bigmcp_pool_servers_total',
    'Number of active MCP servers across all users'
)

POOL_USERS = Gauge(
    'bigmcp_pool_users_total',
    'Number of users with active MCP servers'
)

POOL_VECTOR_STORES = Gauge(
    'bigmcp_pool_vector_stores_cached',
    'Number of cached vector stores'
)

POOL_MAX_SERVERS_PER_USER = Gauge(
    'bigmcp_pool_max_servers_per_user',
    'Maximum servers allowed per user (config)'
)

POOL_MAX_TOTAL_SERVERS = Gauge(
    'bigmcp_pool_max_total_servers',
    'Maximum total servers allowed (config)'
)

# =============================================================================
# Cache Metrics (from CacheBackend.get_stats())
# =============================================================================

CACHE_KEYS = Gauge(
    'bigmcp_cache_keys_total',
    'Total number of keys in cache'
)

CACHE_HITS = Gauge(
    'bigmcp_cache_hits_total',
    'Total cache hits'
)

CACHE_MISSES = Gauge(
    'bigmcp_cache_misses_total',
    'Total cache misses'
)

# =============================================================================
# Session Metrics
# =============================================================================

SSE_SESSIONS = Gauge(
    'bigmcp_sse_sessions_active',
    'Number of active SSE connections'
)

# =============================================================================
# HTTP Metrics (populated by PrometheusMiddleware)
# =============================================================================

HTTP_REQUESTS = Counter(
    'bigmcp_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

HTTP_DURATION = Histogram(
    'bigmcp_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# =============================================================================
# Collection Functions
# =============================================================================

def init_app_info(version: str, edition: str) -> None:
    """
    Initialize application info metric.

    Called once at startup.

    Args:
        version: Application version (e.g., "1.0.0")
        edition: Edition type (community, enterprise, cloud_saas)
    """
    APP_INFO.info({
        'version': version,
        'edition': edition,
    })
    logger.info(f"Metrics initialized: version={version}, edition={edition}")


async def collect_metrics() -> None:
    """
    Collect current state metrics from various sources.

    Called on each /metrics request to ensure fresh data.
    Uses existing get_pool_stats() and get_stats() methods.
    """
    try:
        # Import here to avoid circular imports
        from app.routers.mcp_unified import gateway, mcp_sessions
        from app.core.cache_backend import get_cache_backend

        # Collect pool stats
        pool_stats = gateway.user_server_pool.get_pool_stats()
        POOL_SERVERS.set(pool_stats['total_servers'])
        POOL_USERS.set(pool_stats['total_users'])
        POOL_VECTOR_STORES.set(pool_stats['vector_stores_cached'])
        POOL_MAX_SERVERS_PER_USER.set(pool_stats['max_servers_per_user'])
        POOL_MAX_TOTAL_SERVERS.set(pool_stats['max_total_servers'])

        # Collect cache stats
        backend = get_cache_backend()
        cache_stats = await backend.get_stats()
        CACHE_KEYS.set(cache_stats.get('total_keys', 0))
        CACHE_HITS.set(cache_stats.get('hits', 0))
        CACHE_MISSES.set(cache_stats.get('misses', 0))

        # Collect session count
        SSE_SESSIONS.set(len(mcp_sessions))

    except Exception as e:
        logger.warning(f"Failed to collect metrics: {e}")
