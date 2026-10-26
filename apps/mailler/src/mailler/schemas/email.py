# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email request/response schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SendEmailRequest(BaseModel):
    """Request schema for sending an email."""

    to_email: EmailStr = Field(..., description="Recipient email address")
    to_name: str | None = Field(None, description="Recipient name")
    from_email: EmailStr | None = Field(
        None, description="Sender email (uses default if not provided)"
    )
    from_name: str | None = Field(None, description="Sender name (uses default if not provided)")
    reply_to: EmailStr | None = Field(None, description="Reply-to address")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html_content: str = Field(..., min_length=1, description="HTML content of the email")
    text_content: str | None = Field(None, description="Plain text content (optional)")
    provider: str = Field(..., description="Email provider (brevo, sendgrid, ses, protonmail)")
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


class SendEmailResponse(BaseModel):
    """Response schema for send/schedule operations."""

    id: str = Field(..., description="Email UUID")
    status: str = Field(..., description="Email status")
    message: str = Field(..., description="Status message")
    task_id: str | None = Field(None, description="Celery task ID (for immediate sends)")
