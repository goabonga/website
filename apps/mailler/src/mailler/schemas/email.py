# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email request/response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html_content: str = Field(..., min_length=1, description="HTML content of the email")
    text_content: str | None = Field(None, description="Plain text content (optional)")
    provider: str | None = Field(
        None, description="Provider among those the client may use (its default if omitted)"
    )
    metadata: dict[str, Any] | None = Field(None, description="Custom metadata")

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
