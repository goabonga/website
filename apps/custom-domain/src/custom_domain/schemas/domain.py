# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for domain endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from custom_domain.models.enums import DomainStatus


class DomainCreate(BaseModel):
    """Request schema for creating a domain."""

    domain: str = Field(..., description="The custom domain name")
    owner_id: str = Field(..., description="Owner identifier (e.g., org_id)")
    owner_type: str = Field(
        default="organization",
        description="Type of owner",
    )
    upstream_target: str | None = Field(
        None,
        description="Upstream socket or URL (defaults to client's default)",
    )
    cname_target: str | None = Field(
        None,
        description="CNAME target (defaults to client's default)",
    )
    nginx_template_id: int | None = Field(
        None,
        description="Custom nginx template ID",
    )
    metadata: dict | None = Field(None, description="Custom metadata")


class DomainUpdate(BaseModel):
    """Request schema for updating a domain."""

    upstream_target: str | None = None
    nginx_template_id: int | None = None
    metadata: dict | None = None


class DomainResponse(BaseModel):
    """Response schema for a domain."""

    id: UUID
    domain: str
    status: DomainStatus
    client_id: str
    owner_id: str
    owner_type: str
    upstream_target: str
    cname_target: str
    nginx_template_id: int | None = None
    dns_verified_at: datetime | None = None
    ssl_provisioned_at: datetime | None = None
    ssl_expires_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    metadata: dict | None = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DomainCreateResponse(BaseModel):
    """Response schema for domain creation."""

    id: UUID
    domain: str
    status: DomainStatus
    cname_target: str
    owner_id: str
    owner_type: str
    created_at: datetime
    dns_instructions: str

    model_config = {"from_attributes": True}


class DomainListItem(BaseModel):
    """Minimal domain info for list responses."""

    id: UUID
    domain: str
    status: DomainStatus
    owner_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DomainListResponse(BaseModel):
    """Paginated list of domains."""

    items: list[DomainListItem]
    total: int
    limit: int
    offset: int


class DomainLookupResponse(BaseModel):
    """Response schema for domain lookup."""

    domain: str
    owner_id: str
    owner_type: str
    client_id: str
    status: DomainStatus
    metadata: dict | None = Field(None, validation_alias="metadata_")

    model_config = {"from_attributes": True}


class DomainActionResponse(BaseModel):
    """Response schema for domain actions (verify, provision)."""

    id: UUID
    status: DomainStatus
    message: str
