# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email template request/response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TemplateCreate(BaseModel):
    """Request schema for creating an email template."""

    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
        description=(
            "Template identifier, unique per client "
            "(lowercase letters and digits, single hyphens or underscores between them)"
        ),
    )
    client_id: str | None = Field(
        None,
        description="Owner of the template; administrators only, defaults to the caller's client",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: str | None = Field(None, description="Template description")
    subject_template: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Email subject template (supports Jinja2 variables)",
    )
    mjml_source: str = Field(..., min_length=1, description="MJML source code for the email body")
    plain_text: str | None = Field(None, description="Plain text version of the email (optional)")
    variables: list[str] | None = Field(
        None, description="List of variable names used in the template"
    )
    metadata: dict[str, Any] | None = Field(None, description="Custom metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slug": "welcome-email",
                "name": "Welcome Email",
                "description": "Sent to new users after registration",
                "subject_template": "Welcome to {{ company_name }}, {{ first_name }}!",
                "mjml_source": "<mjml><mj-body><mj-section><mj-column><mj-text>Hello {{ first_name }}!</mj-text></mj-column></mj-section></mj-body></mjml>",
                "variables": ["first_name", "company_name"],
                "metadata": {"category": "onboarding"},
            }
        }
    )


class TemplateUpdate(BaseModel):
    """Request schema for updating an email template."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None)
    subject_template: str | None = Field(None, min_length=1, max_length=500)
    mjml_source: str | None = Field(None, min_length=1)
    plain_text: str | None = Field(None)
    variables: list[str] | None = Field(None)
    metadata: dict[str, Any] | None = Field(None)
    status: str | None = Field(
        None, pattern=r"^(draft|active|archived)$", description="Template status"
    )


class TemplateResponse(BaseModel):
    """Response schema for email template."""

    id: int
    client_id: str
    slug: str
    name: str
    description: str | None
    subject_template: str
    mjml_source: str
    html_compiled: str | None
    plain_text: str | None
    status: str
    variables: list[str] | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateListItem(BaseModel):
    """Template list item for pagination."""

    id: int
    client_id: str
    slug: str
    name: str
    description: str | None
    status: str
    variables: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateListResponse(BaseModel):
    """Paginated template list response."""

    items: list[TemplateListItem]
    total: int
    page: int
    page_size: int
    pages: int


class CompileRequest(BaseModel):
    """Request to compile MJML to HTML."""

    mjml_source: str = Field(..., min_length=1, description="MJML source code")


class CompileResponse(BaseModel):
    """Response with compiled HTML."""

    html: str = Field(..., description="Compiled HTML")
    errors: list[str] | None = Field(None, description="Compilation warnings/errors")


class RenderRequest(BaseModel):
    """Request to render a template with variables."""

    variables: dict[str, Any] = Field(
        default_factory=dict, description="Variables to render in the template"
    )


class RenderResponse(BaseModel):
    """Response with rendered template."""

    subject: str = Field(..., description="Rendered subject line")
    html: str = Field(..., description="Rendered HTML content")
    plain_text: str | None = Field(None, description="Rendered plain text content")
