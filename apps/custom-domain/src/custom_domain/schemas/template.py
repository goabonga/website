# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for template admin endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    """Request schema for creating a template."""

    slug: str = Field(..., description="Unique identifier (slug)")
    name: str = Field(..., description="Display name")
    description: str | None = Field(None, description="Description")
    client_id: str | None = Field(
        None,
        description="OAuth2 client that owns the template; omit for a shared template",
    )
    http_template: str = Field(
        ...,
        description="Jinja2 template for HTTP-only config",
    )
    https_template: str = Field(
        ...,
        description="Jinja2 template for HTTPS config",
    )
    available_variables: list[str] = Field(
        default_factory=list,
        description="List of available template variables",
    )


class TemplateUpdate(BaseModel):
    """Request schema for updating a template."""

    name: str | None = None
    description: str | None = None
    http_template: str | None = None
    https_template: str | None = None
    available_variables: list[str] | None = None
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    """Response schema for a template."""

    id: int
    slug: str
    name: str
    description: str | None = None
    client_id: str | None = None
    http_template: str
    https_template: str
    is_default: bool
    is_active: bool
    available_variables: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateListItem(BaseModel):
    """Template item for list responses."""

    id: int
    slug: str
    name: str
    description: str | None = None
    client_id: str | None = None
    is_default: bool
    is_active: bool
    domains_count: int = 0
    available_variables: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AvailableTemplate(BaseModel):
    """A template a client can choose for its domains (the sources are not exposed)."""

    id: int
    slug: str
    name: str
    description: str | None = None
    shared: bool

    model_config = {"from_attributes": True}


class AvailableTemplateListResponse(BaseModel):
    """Templates available to the calling client."""

    items: list[AvailableTemplate]
    total: int


class TemplateListResponse(BaseModel):
    """Paginated list of templates."""

    items: list[TemplateListItem]
    total: int


class TemplateValidateRequest(BaseModel):
    """Request schema for template validation."""

    test_variables: dict = Field(
        default_factory=dict,
        description="Test variables for rendering",
    )


class TemplateValidateResponse(BaseModel):
    """Response schema for template validation."""

    valid: bool
    rendered_http: str | None = None
    rendered_https: str | None = None
    nginx_syntax_valid: bool = False
    errors: list[str] = []


class TemplateReprovisionRequest(BaseModel):
    """Request schema for reprovisioning domains."""

    only_active: bool = Field(
        default=True,
        description="Only reprovision active domains",
    )
    dry_run: bool = Field(
        default=False,
        description="Perform a dry run without changes",
    )


class ReprovisionError(BaseModel):
    """Error during reprovisioning."""

    domain: str
    error: str


class TemplateReprovisionResponse(BaseModel):
    """Response schema for reprovisioning."""

    domains_affected: int
    success: int
    failed: int
    errors: list[ReprovisionError] = []
