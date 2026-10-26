# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for OAuth2 clients API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClientResponse(BaseModel):
    """Response for a single OAuth2 client."""

    id: uuid.UUID
    client_id: str
    name: str
    description: str | None = None
    homepage_url: str | None = None
    redirect_uris: list[str]
    allowed_scopes: list[str]
    allowed_grant_types: list[str]
    token_endpoint_auth_method: str
    is_confidential: bool
    is_active: bool
    require_pkce: bool
    require_consent: bool
    jwks_uri: str | None = None
    allowed_origins: list[str] | None = None
    access_token_expiry_seconds: int | None = None
    refresh_token_expiry_seconds: int | None = None
    tenant_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateClientRequest(BaseModel):
    """Request body for creating an OAuth2 client."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    homepage_url: str | None = Field(None, max_length=2048)
    redirect_uris: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    allowed_grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"]
    )
    token_endpoint_auth_method: str = Field(default="client_secret_basic", max_length=32)
    is_confidential: bool = True
    require_pkce: bool = True
    require_consent: bool = True
    jwks_uri: str | None = Field(None, max_length=2048)
    allowed_origins: list[str] | None = None
    access_token_expiry_seconds: int | None = None
    refresh_token_expiry_seconds: int | None = None


class UpdateClientRequest(BaseModel):
    """Request body for partially updating an OAuth2 client."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    homepage_url: str | None = Field(None, max_length=2048)
    redirect_uris: list[str] | None = None
    allowed_scopes: list[str] | None = None
    allowed_grant_types: list[str] | None = None
    token_endpoint_auth_method: str | None = Field(None, max_length=32)
    is_confidential: bool | None = None
    is_active: bool | None = None
    require_pkce: bool | None = None
    require_consent: bool | None = None
    jwks_uri: str | None = Field(None, max_length=2048)
    allowed_origins: list[str] | None = None
    access_token_expiry_seconds: int | None = None
    refresh_token_expiry_seconds: int | None = None


class ClientSecretResponse(BaseModel):
    """Response returned when a client secret is generated or rotated."""

    client_id: str
    client_secret: str


class ClientCreatedResponse(ClientResponse):
    """Response returned on client creation — includes the plain-text secret once."""

    client_secret: str | None = None
