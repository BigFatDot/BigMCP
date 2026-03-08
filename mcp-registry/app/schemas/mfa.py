"""
MFA Schemas - Pydantic models for MFA endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MFASetupResponse(BaseModel):
    """Response from MFA setup endpoint."""
    provisioning_uri: str = Field(
        ...,
        description="URI for QR code (otpauth://totp/...)"
    )
    backup_codes: List[str] = Field(
        ...,
        description="10 backup codes for recovery"
    )
    message: str = Field(
        default="Scan QR code with authenticator app, then verify with a code"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "provisioning_uri": "otpauth://totp/BigMCP:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=BigMCP",
                "backup_codes": ["A1B2C3D4", "E5F6G7H8", "..."],
                "message": "Scan QR code with authenticator app, then verify with a code"
            }
        }


class MFAVerifyRequest(BaseModel):
    """Request to verify MFA code."""
    code: str = Field(
        ...,
        min_length=6,
        max_length=8,
        description="6-digit TOTP code or 8-char backup code"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "code": "123456"
            }
        }


class MFAStatusResponse(BaseModel):
    """Response from MFA status endpoint."""
    enabled: bool = Field(
        ...,
        description="Whether MFA is enabled"
    )
    enrolled_at: Optional[str] = Field(
        None,
        description="ISO timestamp when MFA was enabled"
    )
    backup_codes_remaining: Optional[int] = Field(
        None,
        description="Number of unused backup codes"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "enrolled_at": "2026-02-15T10:30:00Z",
                "backup_codes_remaining": 8
            }
        }


class MFAEnableResponse(BaseModel):
    """Response after MFA is enabled."""
    status: str = Field(default="enabled")
    message: str = Field(default="MFA successfully enabled")


class MFADisableResponse(BaseModel):
    """Response after MFA is disabled."""
    status: str = Field(default="disabled")
    message: str = Field(default="MFA disabled")


class MFABackupCodesResponse(BaseModel):
    """Response with new backup codes."""
    backup_codes: List[str] = Field(
        ...,
        description="New backup codes"
    )
    message: str = Field(
        default="New backup codes generated. Previous codes are now invalid."
    )
