# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Personal Access Token API schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PATExpirationPreset(StrEnum):
    """Expiration preset options."""

    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_60 = "60_days"
    DAYS_90 = "90_days"
    DAYS_365 = "365_days"
    NO_EXPIRATION = "no_expiration"
    CUSTOM = "custom"


class CreatePATRequest(BaseModel):
    """Request to create a new PAT."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    scopes: list[str] = Field(min_length=1)
    expiration: PATExpirationPreset = PATExpirationPreset.DAYS_90
    custom_expiration_days: int | None = Field(default=None, ge=1, le=3650)
    tenant_id: str | None = None
    target_client_id: str | None = None


class PATResponse(BaseModel):
    """PAT response (metadata only, never includes token)."""

    id: str
    name: str
    description: str | None
    scopes: list[str]
    token_suffix: str  # Last 4 chars for identification
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    use_count: int
    is_expired: bool
    is_revoked: bool
    tenant_id: str | None = None
    target_client_id: str | None = None


class CreatePATResponse(BaseModel):
    """Response after creating a PAT (includes token once)."""

    token: str  # Full token - ONLY shown once!
    pat: PATResponse


class PATListResponse(BaseModel):
    """Paginated list of PATs."""

    tokens: list[PATResponse]
    total: int
    offset: int
    limit: int


class UpdatePATScopesRequest(BaseModel):
    """Request to update PAT scopes."""

    scopes: list[str] = Field(..., min_length=1, max_length=50)


class RevokePATRequest(BaseModel):
    """Request to revoke a PAT."""

    reason: str | None = Field(default=None, max_length=500)


class BulkRevokeRequest(BaseModel):
    """Request to bulk revoke PATs."""

    user_id: str
    reason: str | None = Field(default=None, max_length=500)


class AdminPATResponse(BaseModel):
    """PAT response for admin view (includes user info)."""

    id: str
    user_id: str
    user_email: str | None
    name: str
    description: str | None
    scopes: list[str]
    token_suffix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    use_count: int
    is_expired: bool
    is_revoked: bool
    tenant_id: str | None = None
    target_client_id: str | None = None


class AdminPATListResponse(BaseModel):
    """Paginated list of PATs for admin view."""

    tokens: list[AdminPATResponse]
    total: int
    offset: int
    limit: int
