# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email request/response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class SendEmailRequest(BaseModel):
    """Request schema for sending an email."""

    to_email: EmailStr = Field(..., description="Recipient email address")
    to_name: str | None = Field(None, description="Recipient name")
    from_email: EmailStr | None = Field(
        None,
        description="Sender email, one of the client's identities (default identity if omitted)",
    )
    from_name: str | None = Field(
        None, description="Sender name, the one of the chosen identity (default if omitted)"
    )
    reply_to: EmailStr | None = Field(None, description="Reply-to address (the client's if fixed)")
    subject: str | None = Field(
        None, min_length=1, max_length=500, description="Email subject (without template_slug)"
    )
    html_content: str | None = Field(
        None, min_length=1, description="HTML content of the email (without template_slug)"
    )
    text_content: str | None = Field(
        None, description="Plain text content (optional, without template_slug)"
    )
    template_slug: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="Slug of one of the client's active templates, rendered by the service",
    )
    variables: dict[str, Any] | None = Field(
        None, description="Variables of the template (with template_slug)"
    )
    provider: str | None = Field(
        None, description="Provider among those the client may use (its default if omitted)"
    )
    metadata: dict[str, Any] | None = Field(None, description="Custom metadata")

    @model_validator(mode="after")
    def _content_or_template(self) -> "SendEmailRequest":
        """An email carries either its content or the slug of a template to render."""
        if self.template_slug:
            if self.subject or self.html_content or self.text_content:
                raise ValueError(
                    "template_slug cannot be combined with subject, html_content or text_content"
                )
        else:
            if not self.subject or not self.html_content:
                raise ValueError("subject and html_content are required without template_slug")
            if self.variables is not None:
                raise ValueError("variables can only be used with template_slug")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "to_email": "user@example.com",
                "to_name": "John Doe",
                "subject": "Hello from Mailler",
                "html_content": "<h1>Hello!</h1><p>This is a test email.</p>",
                "text_content": "Hello! This is a test email.",
                "provider": "brevo",
                "metadata": {"campaign_id": "abc123"},
            }
        }
    )


class ScheduleEmailRequest(SendEmailRequest):
    """Request schema for scheduling an email."""

    scheduled_at: datetime = Field(..., description="When to send the email (ISO 8601)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "to_email": "user@example.com",
                "subject": "Scheduled Email",
                "html_content": "<h1>Hello!</h1>",
                "provider": "brevo",
                "scheduled_at": "2026-01-29T10:00:00Z",
            }
        }
    )


class SendEmailResponse(BaseModel):
    """Response schema for send/schedule operations."""

    id: str = Field(..., description="Email UUID")
    status: str = Field(..., description="Email status")
    message: str = Field(..., description="Status message")
    task_id: str | None = Field(None, description="Celery task ID (for immediate sends)")
    missing_variables: list[str] = Field(
        default_factory=list,
        description="Variables of the template that the request did not provide",
    )


class EmailDetailResponse(BaseModel):
    """Detailed email response."""

    id: str
    to_email: str
    to_name: str | None
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    subject: str
    html_content: str
    text_content: str | None
    provider: str
    provider_message_id: str | None
    status: str
    error_message: str | None
    retry_count: int
    scheduled_at: datetime | None
    queued_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    bounced_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    metadata: dict[str, Any]
    client_id: str | None
    user_id: str | None
    task_id: str | None

    model_config = ConfigDict(from_attributes=True)


class EmailListItem(BaseModel):
    """Email list item for pagination."""

    id: str
    to_email: str
    subject: str
    provider: str
    status: str
    created_at: datetime
    scheduled_at: datetime | None
    sent_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class EmailListResponse(BaseModel):
    """Paginated email list response."""

    items: list[EmailListItem]
    total: int
    page: int
    page_size: int
    pages: int
