"""
Rate limiting middleware for API endpoints.

Implements sliding window counter for rate limiting:
- Configurable per-route limits for different endpoint categories
- Tracks by user_id (Cloud users) or API key (Self-hosted users)
- Supports different limits for sensitive vs public endpoints
- Uses CacheBackend (Redis or in-memory) for counters

User isolation:
- Counter key = rate:{user_key}:{route_pattern}:{window}
- user_key = SHA256(JWT token)[:16] or ip_{client_ip}
- Each user has independent counters, no cross-contamination
"""

import hashlib
import logging
import time
from typing import Dict, Tuple

from fastapi import Request, status, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import settings

logger = logging.getLogger("rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with per-route configuration.

    Uses sliding window counters via CacheBackend.
    Configuration is loaded from settings.RATE_LIMIT_ROUTES.

    Isolation: Each user (identified by JWT hash or IP) gets
    independent per-route counters. User A's requests never
    affect User B's rate limit.
    """

    # Routes to skip rate limiting (health checks, docs, static)
    SKIP_ROUTES = {
        "/health",
        "/mcp/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
    }

    WINDOW_SECONDS = 60  # 1-minute sliding window

    def __init__(self, app):
        super().__init__(app)

        # Load route configurations from settings
        self.route_configs = settings.RATE_LIMIT_ROUTES
        self.default_limit = settings.RATE_LIMIT_DEFAULT
        self.enabled = settings.RATE_LIMIT_ENABLED

    def _backend(self):
        """Get cache backend lazily."""
        from ..core.cache_backend import get_cache_backend
        return get_cache_backend()

    def get_route_config(self, path: str) -> Tuple[str, int]:
        """
        Get rate limit configuration for a path.

        Returns:
            Tuple of (matched_pattern, requests_per_minute)
        """
        for pattern, limit in self.route_configs.items():
            if path.startswith(pattern):
                return pattern, limit

        return "default", self.default_limit

    def extract_user_key(self, request: Request) -> str:
        """
        Extract user identifier from request.

        Priority:
        1. JWT token hash (if present) — unique per user session
        2. Client IP address (fallback) — unique per network origin

        This ensures each user gets independent rate limit counters.
        """
        authorization = request.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            # SHA256 hash ensures uniqueness per user session
            return hashlib.sha256(token.encode()).hexdigest()[:16]

        client_host = request.client.host if request.client else "unknown"
        return f"ip_{client_host}"

    async def dispatch(self, request: Request, call_next):
        """
        Middleware dispatch - check rate limit before processing request.

        Uses sliding window counter: INCR key with 60s TTL per window.
        Each user_key gets isolated counters per route pattern.
        """
        # Skip if rate limiting disabled
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip certain routes
        if path in self.SKIP_ROUTES:
            return await call_next(request)

        # Skip static files and favicon
        if path.startswith("/static") or path == "/favicon.ico":
            return await call_next(request)

        # Get route configuration
        route_pattern, requests_per_minute = self.get_route_config(path)

        # If no matching pattern and default is very high, skip
        if route_pattern == "default" and self.default_limit >= 1000:
            return await call_next(request)

        # Extract per-user identifier (isolation key)
        user_key = self.extract_user_key(request)

        # Sliding window counter key — isolated per user + route + time window
        window = int(time.time() / self.WINDOW_SECONDS)
        counter_key = f"rate:{user_key}:{route_pattern}:{window}"

        backend = self._backend()

        # Increment this user's counter for this route+window
        count = await backend.incr(counter_key)

        # Set expiry on new keys (first request in this window)
        if count == 1:
            await backend.expire(counter_key, self.WINDOW_SECONDS + 5)

        # Calculate remaining for this user
        remaining = max(0, requests_per_minute - count)

        # Check if this user exceeded their rate limit
        if count > requests_per_minute:
            # Estimate retry time
            elapsed_in_window = time.time() % self.WINDOW_SECONDS
            retry_after = max(1, int(self.WINDOW_SECONDS - elapsed_in_window))

            logger.warning(
                f"Rate limit exceeded: user={user_key[:8]}... "
                f"pattern={route_pattern} limit={requests_per_minute}/min "
                f"count={count}"
            )

            return Response(
                content='{"error": "rate_limit_exceeded", '
                        '"message": "Too many requests. Please try again later.", '
                        f'"retry_after": {retry_after}, '
                        f'"limit": {requests_per_minute}, '
                        f'"policy": "{route_pattern}"}}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int((window + 1) * self.WINDOW_SECONDS)),
                    "X-RateLimit-Policy": route_pattern
                },
                media_type="application/json"
            )

        # Process request
        response = await call_next(request)

        # Add rate limit info to response headers (per-user values)
        response.headers["X-RateLimit-Limit"] = str(requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int((window + 1) * self.WINDOW_SECONDS))
        response.headers["X-RateLimit-Policy"] = route_pattern

        return response
