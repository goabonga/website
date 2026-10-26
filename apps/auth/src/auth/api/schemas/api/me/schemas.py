# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for /api/v1/me endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ProfileResponse(BaseModel):
    """User profile response."""

    sub: str
    nickname: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None


class ProfileUpdateRequest(BaseModel):
    """Profile update request."""

    nickname: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None


class PasswordChangeRequest(BaseModel):
    """Password change request."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class MFAStatusResponse(BaseModel):
    """MFA status response."""

    totp_enabled: bool
    backup_codes_remaining: int | None = None
    backup_codes_total: int | None = None


class TOTPSetupResponse(BaseModel):
    """TOTP setup response."""

    secret: str
    qr_code: str


class TOTPVerifyRequest(BaseModel):
    """TOTP verification request."""

    code: str


class TOTPEnableResponse(BaseModel):
    """TOTP enable response with backup codes."""

    message: str
    backup_codes: list[str]


class BackupCodesResponse(BaseModel):
    """Backup codes response."""

    backup_codes: list[str]


class SessionResponse(BaseModel):
    """Session response."""

    id: uuid.UUID
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class PATCreateRequest(BaseModel):
    """Create PAT request."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    description: str | None = None
    expiration_preset: str = "30_days"
    custom_expiration_days: int | None = None


class PATUpdateRequest(BaseModel):
    """Update PAT scopes request."""

    scopes: list[str]


class PATResponse(BaseModel):
    """PAT response."""

    id: uuid.UUID
    name: str
    description: str | None = None
    token_suffix: str
    scopes: list[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    use_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PATCreateResponse(BaseModel):
    """PAT creation response with full token (shown only once)."""

    id: uuid.UUID
    name: str
    token: str
    scopes: list[str]
    expires_at: datetime | None = None
    created_at: datetime


class ApplicationResponse(BaseModel):
    """Authorized application response."""

    client_id: str
    name: str
    description: str | None = None
    homepage_url: str | None = None
    scopes: list[str] = Field(default_factory=list)


class OrganisationSummaryResponse(BaseModel):
    """Organisation summary for /me/organisations."""

    id: uuid.UUID
    slug: str
    display_name: str
    role_name: str | None = None
    role_display_name: str | None = None
    joined_at: datetime | None = None

    model_config = {"from_attributes": True}


class CreateOrganisationRequest(BaseModel):
    """Create organisation request."""

    slug: str = Field(..., min_length=2, max_length=63, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
    display_name: str = Field(..., min_length=1, max_length=255)
