# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for client admin endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from custom_domain.schemas.validators import (
    validate_upstream,
    validate_webhook_secret,
    validate_webhook_url,
)


class ClientCreate(BaseModel):
    """Request schema for creating a client."""

    client_id: str = Field(..., description="OAuth2 client ID")
    name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Description")
    default_upstream_target: str = Field(
        ...,
        description="Default upstream: absolute socket path or host:port",
    )
    default_cname_target: str = Field(
        ...,
        description="Default CNAME target",
    )
    default_nginx_template_id: int | None = Field(
        None,
        description="Default nginx template ID",
    )
    max_domains: int | None = Field(
        None,
        description="Maximum number of domains (null = unlimited)",
    )
    metadata: dict | None = Field(None, description="Custom metadata")
    webhook_url: str | None = Field(
        None, description="URL that receives signed status notifications (https)"
    )
    webhook_secret: str | None = Field(
        None, description="HMAC secret shared with the client (at least 32 characters)"
    )

    _check_upstream = field_validator("default_upstream_target")(validate_upstream)
    _check_webhook_url = field_validator("webhook_url")(validate_webhook_url)
    _check_webhook_secret = field_validator("webhook_secret")(validate_webhook_secret)


class ClientUpdate(BaseModel):
    """Request schema for updating a client."""

    name: str | None = None
    description: str | None = None
    default_upstream_target: str | None = None
    default_cname_target: str | None = None
    default_nginx_template_id: int | None = None
    max_domains: int | None = None
    metadata: dict | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None

    _check_upstream = field_validator("default_upstream_target")(validate_upstream)
    _check_webhook_url = field_validator("webhook_url")(validate_webhook_url)
    _check_webhook_secret = field_validator("webhook_secret")(validate_webhook_secret)


class ClientResponse(BaseModel):
    """Response schema for a client."""

    id: int
    client_id: str
    name: str
    description: str | None = None
    default_upstream_target: str
    default_cname_target: str
    default_nginx_template_id: int | None = None
    max_domains: int | None = None
    is_active: bool
    webhook_url: str | None = None
    has_webhook_secret: bool = Field(False, validation_alias="webhook_secret")
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("has_webhook_secret", mode="before")
    @classmethod
    def _secret_is_never_exposed(cls, value: object) -> bool:
        """Report whether a secret is set; the secret itself is never returned."""
        return bool(value)


class ClientListItem(BaseModel):
    """Client item for list responses."""

    id: int
    client_id: str
    name: str
    default_upstream_target: str
    default_cname_target: str
    default_nginx_template_id: int | None = None
    max_domains: int | None = None
    is_active: bool
    domains_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    """Paginated list of clients."""

    items: list[ClientListItem]
    total: int
