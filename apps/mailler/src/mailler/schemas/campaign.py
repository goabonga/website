# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email campaign request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==================== Campaign Schemas ====================


class CampaignCreate(BaseModel):
    """Request schema for creating a campaign."""

    name: str = Field(..., min_length=1, max_length=255, description="Campaign name")
    description: str | None = Field(None, description="Campaign description")
    template_id: int | None = Field(None, description="Email template ID to use")
    group_id: int | None = Field(None, description="Contact group ID to send to")
    from_name: str | None = Field(None, max_length=255, description="Sender name override")
    from_email: EmailStr | None = Field(None, description="Sender email override")
    reply_to: EmailStr | None = Field(None, description="Reply-to address")
    provider: str | None = Field(
        None, description="Email provider (brevo, sendgrid, ses, protonmail)"
    )
    subject_override: str | None = Field(None, max_length=500, description="Subject line override")
    scheduled_at: datetime | None = Field(
        None, description="When to send (ISO 8601). Leave empty for draft."
    )
    metadata: dict[str, Any] | None = Field(None, description="Custom metadata")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "January Newsletter",
                "description": "Monthly newsletter for January 2026",
                "template_id": 1,
                "group_id": 2,
                "provider": "brevo",
                "scheduled_at": "2026-01-15T09:00:00Z",
            }
        }
    )


class CampaignUpdate(BaseModel):
    """Request schema for updating a campaign."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None)
    template_id: int | None = Field(None)
    group_id: int | None = Field(None)
    from_name: str | None = Field(None, max_length=255)
    from_email: EmailStr | None = Field(None)
    reply_to: EmailStr | None = Field(None)
    provider: str | None = Field(None)
    subject_override: str | None = Field(None, max_length=500)
    scheduled_at: datetime | None = Field(None)
    metadata: dict[str, Any] | None = Field(None)


class CampaignStats(BaseModel):
    """Campaign statistics."""

    total_recipients: int
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    bounced_count: int
    complained_count: int
    failed_count: int
    progress_percent: float
    open_rate: float
    click_rate: float
    bounce_rate: float
    complaint_rate: float


class CampaignTemplateEmbed(BaseModel):
    """Embedded template info in campaign response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subject: str | None = None


class CampaignGroupEmbed(BaseModel):
    """Embedded contact group info in campaign response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    member_count: int = 0


class CampaignResponse(BaseModel):
    """Response schema for a campaign."""

    id: int
    client_id: str
    name: str
    description: str | None
    template_id: int | None
    group_id: int | None
    template: CampaignTemplateEmbed | None = None
    group: CampaignGroupEmbed | None = None
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    from_name: str | None
    from_email: str | None
    reply_to: str | None
    provider: str | None
    subject_override: str | None
    task_id: str | None
    metadata: dict[str, Any]
    stats: CampaignStats
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListItem(BaseModel):
    """Campaign list item for pagination."""

    id: int
    name: str
    description: str | None
    status: str
    template_id: int | None
    group_id: int | None
    template: CampaignTemplateEmbed | None = None
    group: CampaignGroupEmbed | None = None
    total_recipients: int
    sent_count: int
    progress_percent: float = 0.0
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    """Paginated campaign list response."""

    items: list[CampaignListItem]
    total: int
    page: int
    page_size: int
    pages: int


# ==================== Email Send Schemas ====================


class EmailSendResponse(BaseModel):
    """Response schema for an email send."""

    id: UUID
    campaign_id: int
    contact_id: UUID | None
    recipient_email: str
    recipient_name: str | None
    status: str
    queued_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    clicked_at: datetime | None
    bounced_at: datetime | None
    error_message: str | None
    message_id: str | None
    metadata: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailSendListItem(BaseModel):
    """Email send list item for pagination."""

    id: UUID
    recipient_email: str
    recipient_name: str | None
    status: str
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class EmailSendListResponse(BaseModel):
    """Paginated email send list response."""

    items: list[EmailSendListItem]
    total: int
    page: int
    page_size: int
    pages: int


# ==================== Campaign Action Schemas ====================


class ScheduleCampaignRequest(BaseModel):
    """Request to schedule a campaign."""

    scheduled_at: datetime = Field(..., description="When to send (ISO 8601)")


class ScheduleCampaignResponse(BaseModel):
    """Response for scheduling a campaign."""

    campaign_id: int
    status: str
    scheduled_at: datetime
    message: str


class SendCampaignResponse(BaseModel):
    """Response for starting a campaign send."""

    campaign_id: int
    status: str
    task_id: str | None
    total_recipients: int
    message: str


class PauseCampaignResponse(BaseModel):
    """Response for pausing a campaign."""

    campaign_id: int
    status: str
    sent_count: int
    message: str


class CampaignPreview(BaseModel):
    """Campaign preview with rendered content."""

    subject: str
    html: str
    plain_text: str | None
    recipient_count: int
