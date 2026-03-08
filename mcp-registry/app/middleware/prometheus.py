"""
Prometheus metrics middleware.

Records HTTP request duration and counts for observability.
Follows the same patterns as rate_limit.py and security_headers.py.

Metrics recorded:
- bigmcp_http_requests_total: Counter with method, endpoint, status labels
- bigmcp_http_request_duration_seconds: Histogram with method, endpoint labels

Endpoint normalization prevents cardinality explosion by replacing
dynamic path segments (UUIDs, numeric IDs) with placeholders.
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..core.metrics import HTTP_REQUESTS, HTTP_DURATION

logger = logging.getLogger(__name__)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware that records HTTP request metrics for Prometheus.

    Tracks:
    - Request count by method/endpoint/status_code
    - Request duration histogram by method/endpoint

    Follows the same structure as RateLimitMiddleware.
    """

    # Routes to skip (same as rate_limit.py for consistency)
    SKIP_ROUTES = {
        "/health",
        "/mcp/health",
        "/ready",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip routes that shouldn't be tracked
        if path in self.SKIP_ROUTES:
            return await call_next(request)

        # Skip static files
        if path.startswith("/static") or path == "/favicon.ico":
            return await call_next(request)

        # Normalize endpoint for cardinality control
        endpoint = self._normalize_endpoint(path)
        method = request.method

        # Time the request
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)

        # Record metrics
        HTTP_REQUESTS.labels(
            method=method,
            endpoint=endpoint,
            status=status_code
        ).inc()

        HTTP_DURATION.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

        return response

    def _normalize_endpoint(self, path: str) -> str:
        """
        Normalize path to prevent label cardinality explosion.

        Replaces dynamic segments with placeholders:
        - UUIDs: /api/v1/users/550e8400-e29b-... → /api/v1/users/{id}
        - Numeric IDs: /api/v1/items/123 → /api/v1/items/{id}

        Args:
            path: Original request path

        Returns:
            Normalized path with placeholders
        """
        parts = path.split('/')
        normalized = []

        for part in parts:
            # UUID pattern (36 chars with dashes)
            if len(part) == 36 and part.count('-') == 4:
                normalized.append('{id}')
            # Numeric ID
            elif part.isdigit():
                normalized.append('{id}')
            # Short hash/token (8-32 hex chars)
            elif len(part) >= 8 and len(part) <= 32 and all(c in '0123456789abcdef' for c in part.lower()):
                normalized.append('{token}')
            else:
                normalized.append(part)

        return '/'.join(normalized)
