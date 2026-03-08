"""
Application configuration and settings.

Manages environment variables and application-wide configuration.
"""

import os
import secrets
from typing import Optional
from functools import lru_cache


class Settings:
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "MCPHub"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://mcphub:mcphub@localhost:5432/mcphub"
    )

    # Security - JWT
    # CRITICAL: Never auto-generate in production - JWT tokens would be invalidated on restart
    SECRET_KEY: Optional[str] = os.getenv("SECRET_KEY")
    ALGORITHM: str = "HS256"
    # Access token: 1 hour default (Claude Desktop will auto-refresh before expiry)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    # Refresh token: 30 days default (balances security and UX for Claude Desktop)
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # Security - API Keys
    API_KEY_PREFIX: str = "mcphub_sk_"
    API_KEY_LENGTH: int = 32  # chars after prefix

    # Security - Passwords
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = False

    # Security - Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    # Rate limit configuration per route pattern (requests per minute)
    # More restrictive limits for sensitive endpoints
    RATE_LIMIT_ROUTES: dict[str, int] = {
        "/api/v1/auth/": 20,          # Login/register - strict to prevent brute force
        "/api/v1/credentials/": 50,   # Sensitive - secrets access
        "/api/v1/api-keys/": 30,      # Very sensitive - key creation/revocation
        "/api/v1/org-credentials/": 50,  # Organization credentials
        "/api/v1/marketplace/": 100,  # Public marketplace
        "/api/v1/oauth/": 30,         # OAuth endpoints - strict to prevent abuse
    }

    # Default rate limit for unmatched routes
    RATE_LIMIT_DEFAULT: int = int(os.getenv("RATE_LIMIT_DEFAULT", "200"))

    # CORS
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = ["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-API-Key"]

    # Encryption (for credentials)
    ENCRYPTION_KEY: Optional[str] = os.getenv("ENCRYPTION_KEY")

    # OAuth Providers (future)
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    GITHUB_CLIENT_ID: Optional[str] = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET: Optional[str] = os.getenv("GITHUB_CLIENT_SECRET")

    # =====================================
    # Email Service (SMTP)
    # =====================================
    # SMTP server configuration (Hostinger for SaaS: 465/SSL, custom for Enterprise)
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL: Optional[str] = os.getenv("SMTP_FROM_EMAIL")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "BigMCP")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "true").lower() == "true"

    # Password reset configuration
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_HOURS", "24"))

    # Invitation configuration
    INVITATION_EXPIRE_DAYS: int = int(os.getenv("INVITATION_EXPIRE_DAYS", "7"))

    # Email verification (SaaS only - blocks login until email verified)
    # Disabled by default for Enterprise/Community (self-hosted)
    # Set to "true" to require email verification before login
    REQUIRE_EMAIL_VERIFICATION: bool = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"

    # Domain (for redirects after payment)
    domain: Optional[str] = os.getenv("DOMAIN")

    # LemonSqueezy (Cloud SaaS billing)
    lemonsqueezy_api_key: Optional[str] = os.getenv("LEMONSQUEEZY_API_KEY")
    lemonsqueezy_webhook_secret: Optional[str] = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET")
    lemonsqueezy_store_id: Optional[str] = os.getenv("LEMONSQUEEZY_STORE_ID")
    # Variant IDs for subscription products
    lemonsqueezy_individual_variant_id: Optional[str] = os.getenv("LEMONSQUEEZY_INDIVIDUAL_VARIANT_ID")
    lemonsqueezy_team_variant_id: Optional[str] = os.getenv("LEMONSQUEEZY_TEAM_VARIANT_ID")
    lemonsqueezy_enterprise_variant_id: Optional[str] = os.getenv("LEMONSQUEEZY_ENTERPRISE_VARIANT_ID")

    # =====================================
    # Edition System
    # =====================================
    # Explicit edition override (optional, auto-detected if not set)
    # Values: "community", "enterprise", "cloud_saas"
    EDITION: Optional[str] = os.getenv("EDITION")

    # Enterprise Edition - License key (JWT signed with ES256)
    # Obtained from bigmcp.cloud after purchase
    LICENSE_KEY: Optional[str] = os.getenv("LICENSE_KEY")

    # Cloud SaaS Edition - Secret token (BigFatDot internal only)
    # Only set on bigmcp.cloud production deployment
    SAAS_TOKEN: Optional[str] = os.getenv("SAAS_TOKEN")

    # Platform Admin Token (Cloud SaaS only)
    # Used to validate instance admin for bigmcp.cloud
    # Must be a strong, random token (never commit to repo)
    PLATFORM_ADMIN_TOKEN: Optional[str] = os.getenv("PLATFORM_ADMIN_TOKEN")

    # License signing private key (Cloud SaaS only - NEVER commit)
    # Used to generate Enterprise LICENSE_KEY tokens
    LICENSE_SIGNING_PRIVATE_KEY: Optional[str] = os.getenv("LICENSE_SIGNING_PRIVATE_KEY")

    # Public sector coupon code (Cloud SaaS only - NEVER commit)
    # Applied server-side for whitelisted domains
    PUBLIC_SECTOR_COUPON_CODE: Optional[str] = os.getenv("PUBLIC_SECTOR_COUPON_CODE")

    # Redis
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    REDIS_PREFIX: str = os.getenv("REDIS_PREFIX", "bigmcp:")
    REDIS_DEFAULT_TTL: int = int(os.getenv("REDIS_DEFAULT_TTL", "3600"))

    # Server Pool limits
    POOL_MAX_SERVERS_PER_USER: int = int(os.getenv("POOL_MAX_SERVERS_PER_USER", "10"))
    POOL_MAX_TOTAL_SERVERS: int = int(os.getenv("POOL_MAX_TOTAL_SERVERS", "50"))
    POOL_CLEANUP_TIMEOUT_MINUTES: int = int(os.getenv("POOL_CLEANUP_TIMEOUT_MINUTES", "5"))
    POOL_CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("POOL_CLEANUP_INTERVAL_SECONDS", "30"))

    # MCP Server
    MCP_SERVER_TIMEOUT: int = int(os.getenv("MCP_SERVER_TIMEOUT", "300"))  # seconds
    MCP_SERVER_MAX_RETRIES: int = int(os.getenv("MCP_SERVER_MAX_RETRIES", "3"))

    # Vector Store
    VECTOR_STORE_PATH: str = os.getenv("VECTOR_STORE_PATH", "./data/vector_store")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "mistral-embed")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Development
    RELOAD: bool = os.getenv("RELOAD", "false").lower() == "true"

    def __init__(self):
        """Validate critical settings on initialization - fail-fast for security."""
        # SECRET_KEY: Required in production, auto-generated ONLY in debug mode
        if not self.SECRET_KEY:
            if self.DEBUG:
                # Dev mode: auto-generate (with warning via logging when imported)
                object.__setattr__(self, 'SECRET_KEY', secrets.token_urlsafe(32))
                object.__setattr__(self, '_secret_key_auto_generated', True)
            else:
                raise ValueError(
                    "CRITICAL: SECRET_KEY must be set in production. "
                    "Auto-generation is disabled to prevent JWT invalidation on restart. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

        # ENCRYPTION_KEY: Required in production for credential encryption
        if not self.ENCRYPTION_KEY and not self.DEBUG:
            raise ValueError(
                "CRITICAL: ENCRYPTION_KEY must be set in production. "
                "Without it, encrypted credentials would be lost on restart. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Convenience access
settings = get_settings()
