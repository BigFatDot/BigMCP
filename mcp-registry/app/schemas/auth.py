"""
Pydantic schemas for authentication.

Defines request/response models for auth endpoints.
"""

from typing import Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, validator


# ===== User Registration =====

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength."""
        from ..core.config import settings

        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")

        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        return v


# ===== User Login =====

class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str
    mfa_code: Optional[str] = Field(
        None,
        min_length=6,
        max_length=8,
        description="6-digit TOTP code or 8-char backup code (required if MFA enabled)"
    )


class MFAChallengeResponse(BaseModel):
    """Response when MFA is required."""
    mfa_required: bool = True
    mfa_token: str = Field(
        ...,
        description="Temporary token to complete MFA verification"
    )
    message: str = Field(
        default="MFA verification required. Provide mfa_code to complete login."
    )


class MFALoginRequest(BaseModel):
    """Complete login with MFA code using mfa_token."""
    mfa_token: str = Field(
        ...,
        description="Temporary token from login response"
    )
    mfa_code: str = Field(
        ...,
        min_length=6,
        max_length=8,
        description="6-digit TOTP code or 8-char backup code"
    )


class TokenResponse(BaseModel):
    """Token response after login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RegisterResponse(BaseModel):
    """Registration response with user info and tokens (auto-login)."""
    user: "UserResponse"
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


# ===== User Response =====

class UserResponse(BaseModel):
    """User information response."""
    id: UUID
    email: str
    name: Optional[str]
    avatar_url: Optional[str]
    auth_provider: str
    email_verified: bool = False
    created_at: datetime
    last_login_at: Optional[datetime]
    organization: Optional[dict] = None  # Organization info {id, name, slug}

    class Config:
        from_attributes = True


# ===== API Key Schemas =====

class APIKeyCreate(BaseModel):
    """Create API key request."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: list[str] = Field(default_factory=list)
    tool_group_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None

    @validator('name')
    def validate_name(cls, v):
        """Validate name is not empty."""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @validator('scopes')
    def validate_scopes(cls, v):
        """Validate scopes are valid."""
        from ..models.api_key import APIKeyScope

        valid_scopes = [scope.value for scope in APIKeyScope]
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}. Valid scopes: {', '.join(valid_scopes)}")
        return v


class APIKeyResponse(BaseModel):
    """API key response (without secret)."""
    id: UUID
    name: str
    description: Optional[str]
    key_prefix: str
    scopes: list[str]
    tool_group_id: Optional[UUID]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime]
    last_used_ip: Optional[str]

    class Config:
        from_attributes = True


class APIKeyCreateResponse(BaseModel):
    """Response when creating API key (includes secret ONCE)."""
    api_key: APIKeyResponse
    secret: str = Field(..., description="IMPORTANT: Save this secret! It will only be shown once.")

    class Config:
        from_attributes = True


class APIKeyUpdate(BaseModel):
    """Update API key request."""
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[list[str]] = None
    is_active: Optional[bool] = None

    @validator('scopes')
    def validate_scopes(cls, v):
        """Validate scopes are valid."""
        if v is None:
            return v

        from ..models.api_key import APIKeyScope

        valid_scopes = [scope.value for scope in APIKeyScope]
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}")
        return v


# ===== Profile Management =====

class ProfileUpdate(BaseModel):
    """Update profile request."""
    name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[str] = Field(None, max_length=500)


# ===== Password Management =====

class PasswordChange(BaseModel):
    """Change password request."""
    old_password: str
    new_password: str = Field(..., min_length=8)

    @validator('new_password')
    def validate_new_password(cls, v, values):
        """Validate new password."""
        from ..core.config import settings

        if 'old_password' in values and v == values['old_password']:
            raise ValueError("New password must be different from old password")

        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")

        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        return v


class PasswordReset(BaseModel):
    """Password reset request."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with token."""
    token: str
    new_password: str = Field(..., min_length=8)

    @validator('new_password')
    def validate_new_password(cls, v):
        """Validate new password meets requirements."""
        from ..core.config import settings

        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")

        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if settings.PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        return v


# ===== OAuth (future) =====

class OAuthProvider(BaseModel):
    """OAuth provider info."""
    provider: str  # "google", "github", etc.
    authorization_url: str


class OAuthCallback(BaseModel):
    """OAuth callback data."""
    code: str
    state: Optional[str] = None


# Resolve forward references for RegisterResponse
RegisterResponse.model_rebuild()
