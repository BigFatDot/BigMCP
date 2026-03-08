"""
Security Headers Middleware.

Adds essential security headers to all HTTP responses:
- Strict-Transport-Security (HSTS): Force HTTPS
- X-Content-Type-Options: Prevent MIME sniffing
- X-Frame-Options: Prevent clickjacking
- X-XSS-Protection: Legacy XSS protection (deprecated but harmless)
- Content-Security-Policy: Restrict content sources
- Referrer-Policy: Control referrer information
- Permissions-Policy: Restrict browser features
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers are configured for an API backend that serves JSON responses.
    For frontend/HTML applications, CSP policy would need adjustment.
    """

    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Skip HSTS in debug mode (localhost doesn't support HTTPS)
        if not self.debug:
            # HSTS: Force HTTPS for 1 year, include subdomains
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking - API should never be framed
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection (modern browsers use CSP instead)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy for API responses
        # - default-src 'none': Block everything by default
        # - frame-ancestors 'none': Prevent framing (like X-Frame-Options)
        # Note: OAuth consent page and /docs need adjusted CSP, handled below
        if request.url.path.startswith("/docs") or request.url.path.startswith("/api/v1/oauth/authorize"):
            # Swagger UI and OAuth consent page need scripts and styles
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'"
            )
        else:
            # Strict CSP for API endpoints
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        # Control referrer information sent with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features (geolocation, camera, etc.)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Prevent caching of sensitive API responses
        # Individual endpoints can override this if needed
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response
