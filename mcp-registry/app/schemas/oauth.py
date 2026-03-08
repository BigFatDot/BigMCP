"""
OAuth 2.0 Pydantic schemas for request/response validation.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from datetime import datetime


# ===== OAuth Client Schemas =====

class OAuthClientCreate(BaseModel):
    """Schema for creating a new OAuth client."""
    name: str = Field(..., min_length=1, max_length=255, description="Client application name")
    description: Optional[str] = Field(None, description="Client description")
    redirect_uris: List[str] = Field(..., min_items=1, description="Allowed redirect URIs")
    allowed_scopes: Optional[List[str]] = Field(
        default=["mcp:execute", "mcp:read"],
        description="Scopes this client can request"
    )
    is_trusted: bool = Field(default=False, description="Skip consent screen for trusted clients")


class OAuthClientResponse(BaseModel):
    """Schema for OAuth client response."""
    id: UUID
    client_id: str
    name: str
    description: Optional[str]
    redirect_uris: List[str]
    allowed_scopes: List[str]
    is_active: bool
    is_trusted: bool
    created_at: datetime

    # Only returned on creation
    client_secret: Optional[str] = Field(None, description="Client secret (only on creation)")

    class Config:
        from_attributes = True


# ===== OAuth Authorization Flow Schemas =====

class AuthorizationRequest(BaseModel):
    """Schema for OAuth authorization request (GET /oauth/authorize)."""
    response_type: str = Field("code", description="Must be 'code'")
    client_id: str = Field(..., description="OAuth client ID")
    redirect_uri: str = Field(..., description="Redirect URI")
    scope: Optional[str] = Field("mcp:execute", description="Requested scopes (space-separated)")
    state: Optional[str] = Field(None, description="Client state for CSRF protection")

    # PKCE parameters (recommended for public clients)
    code_challenge: Optional[str] = Field(None, description="PKCE code challenge")
    code_challenge_method: Optional[str] = Field("S256", description="PKCE method (S256 or plain)")


class AuthorizationResponse(BaseModel):
    """Schema for OAuth authorization response (redirect)."""
    code: str = Field(..., description="Authorization code")
    state: Optional[str] = Field(None, description="Client state (if provided)")


class TokenRequest(BaseModel):
    """Schema for OAuth token request (POST /oauth/token)."""
    grant_type: str = Field("authorization_code", description="Must be 'authorization_code'")
    code: str = Field(..., description="Authorization code")
    redirect_uri: str = Field(..., description="Redirect URI (must match)")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: Optional[str] = Field(None, description="Client secret (for confidential clients)")

    # PKCE parameter
    code_verifier: Optional[str] = Field(None, description="PKCE code verifier")


class TokenResponse(BaseModel):
    """Schema for OAuth token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token (optional)")
    scope: str = Field(..., description="Granted scopes")

    # Additional context
    user_id: UUID = Field(..., description="User ID")
    organization_id: UUID = Field(..., description="Organization ID")


# ===== Consent Page Schema =====

class ConsentRequest(BaseModel):
    """Schema for user consent (POST from consent page)."""
    client_id: str
    redirect_uri: str
    scopes: List[str]
    state: Optional[str]
    code_challenge: Optional[str]
    code_challenge_method: Optional[str]
    approved: bool = Field(..., description="Whether user approved the request")


# ===== Dynamic Client Registration (RFC 7591) Schemas =====

class DynamicClientRegistrationRequest(BaseModel):
    """
    Schema for Dynamic Client Registration (RFC 7591).

    Claude Desktop POSTs this to /register to automatically obtain credentials.
    """
    redirect_uris: List[str] = Field(..., min_items=1, description="Array of redirect URIs")
    token_endpoint_auth_method: Optional[str] = Field(
        "client_secret_post",
        description="Token endpoint authentication method"
    )
    grant_types: Optional[List[str]] = Field(
        default=["authorization_code", "refresh_token"],
        description="OAuth grant types"
    )
    response_types: Optional[List[str]] = Field(
        default=["code"],
        description="OAuth response types"
    )
    client_name: Optional[str] = Field(None, description="Human-readable client name")
    client_uri: Optional[str] = Field(None, description="Client homepage URL")
    logo_uri: Optional[str] = Field(None, description="Client logo URL")
    scope: Optional[str] = Field(
        "mcp:execute mcp:read",
        description="Space-separated scopes"
    )
    contacts: Optional[List[str]] = Field(None, description="Contact emails")
    tos_uri: Optional[str] = Field(None, description="Terms of Service URL")
    policy_uri: Optional[str] = Field(None, description="Privacy Policy URL")


class DynamicClientRegistrationResponse(BaseModel):
    """
    Schema for Dynamic Client Registration response (RFC 7591).

    Returns client credentials to Claude Desktop.
    Note: exclude_none=True to avoid Zod validation errors in mcp-remote
    """
    client_id: str = Field(..., description="OAuth 2.0 client identifier")
    client_secret: str = Field(..., description="OAuth 2.0 client secret")
    client_id_issued_at: int = Field(..., description="Timestamp when client_id was issued")
    client_secret_expires_at: int = Field(
        0,
        description="Timestamp when client_secret expires (0 = never)"
    )

    # Echo back the registered metadata
    redirect_uris: List[str]
    token_endpoint_auth_method: str
    grant_types: List[str]
    response_types: List[str]
    client_name: Optional[str] = None
    client_uri: Optional[str] = None
    logo_uri: Optional[str] = None
    scope: str
    contacts: Optional[List[str]] = None
    tos_uri: Optional[str] = None
    policy_uri: Optional[str] = None

    class Config:
        # Exclude None values from JSON output (fixes mcp-remote Zod validation)
        exclude_none = True
