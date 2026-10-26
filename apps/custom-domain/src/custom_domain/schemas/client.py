# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for client admin endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    """Request schema for creating a client."""

    client_id: str = Field(..., description="OAuth2 client ID")
    name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Description")
    default_upstream_target: str = Field(
        ...,
        description="Default upstream socket or URL",
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


class ClientUpdate(BaseModel):
    """Request schema for updating a client."""

    name: str | None = None
    description: str | None = None
    default_upstream_target: str | None = None
    default_cname_target: str | None = None
    default_nginx_template_id: int | None = None
    max_domains: int | None = None
    metadata: dict | None = None


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
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
