"""Pydantic schemas for instance-branding endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


HEX_COLOR_PATTERN = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"


class BrandingResponse(BaseModel):
    """Public read view served by GET /api/v1/instance/branding."""

    instance_name: str
    instance_tagline: str
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str
    support_email: Optional[str] = None
    instance_url: Optional[str] = None
    legal_entity: Optional[str] = None
    welcome_message: Optional[str] = None
    setup_completed: bool
    customized: bool


class BrandingUpdate(BaseModel):
    """Admin PATCH payload. All fields optional — only the ones provided
    are persisted. Send an empty string to clear a field back to defaults."""

    instance_name: Optional[str] = Field(default=None, max_length=120)
    instance_tagline: Optional[str] = Field(default=None, max_length=240)
    logo_url: Optional[str] = Field(default=None, max_length=2048)
    favicon_url: Optional[str] = Field(default=None, max_length=2048)
    primary_color: Optional[str] = Field(default=None, max_length=16)
    support_email: Optional[str] = Field(default=None, max_length=254)
    instance_url: Optional[str] = Field(default=None, max_length=2048)
    legal_entity: Optional[str] = Field(default=None, max_length=240)
    # 4KB soft cap on the markdown welcome body — enough for a
    # paragraph and a couple of links. Longer content belongs in docs.
    welcome_message: Optional[str] = Field(default=None, max_length=4096)

    @field_validator("primary_color")
    @classmethod
    def _validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        import re

        if not re.match(HEX_COLOR_PATTERN, v):
            raise ValueError(
                "primary_color must be a CSS hex string like '#D97757' or '#fff'"
            )
        return v

    @field_validator("logo_url", "favicon_url", "instance_url")
    @classmethod
    def _validate_url_or_data(cls, v: Optional[str]) -> Optional[str]:
        # Allow http(s) and data: URLs. Reject anything else to avoid
        # javascript: / file: shenanigans in the rendered <img src>.
        if v is None or v == "":
            return v
        lo = v.lower()
        if lo.startswith(("http://", "https://", "data:image/")):
            return v
        raise ValueError(
            "URL must start with http://, https:// or data:image/"
        )


class SetupCompletionResponse(BaseModel):
    setup_completed: bool
