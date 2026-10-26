# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Inbound email schemas (Brevo-compatible format)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# ============================================================================
# Brevo-compatible webhook payload schemas
# ============================================================================


class Mailbox(BaseModel):
    """Email address with optional name (Brevo format)."""

    Address: str
    Name: str | None = None


class AttachmentPayload(BaseModel):
    """Attachment metadata in webhook payload (Brevo format)."""

    Name: str
    ContentType: str
    ContentLength: int
    ContentID: str = ""
    DownloadToken: str


class InboundEmailPayload(BaseModel):
    """Single inbound email in Brevo-compatible format."""

    Uuid: list[str]
    MessageId: str
    InReplyTo: str | None = None
    From: Mailbox
    To: list[Mailbox]
    Recipients: list[Mailbox]
    Cc: list[Mailbox] = []
    ReplyTo: Mailbox | None = None
    SentAtDate: str
    Subject: str
    RawHtmlBody: str | None = None
    RawTextBody: str | None = None
    ExtractedMarkdownMessage: str = ""
    ExtractedMarkdownSignature: str | None = None
    SpamScore: float = 0.0
    Attachments: list[AttachmentPayload] = []
    Headers: dict[str, str] = {}


class InboundWebhookPayload(BaseModel):
    """Top-level Brevo-compatible webhook payload."""

    items: list[InboundEmailPayload]


# ============================================================================
# API response schemas
# ============================================================================


class InboundEmailListItem(BaseModel):
    """Inbound email list item for pagination."""

    id: str
    from_email: str
    from_name: str | None
    subject: str
    status: str
    received_at: datetime | None
    forwarded_at: datetime | None
    created_at: datetime
    attachment_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class InboundEmailListResponse(BaseModel):
    """Paginated inbound email list response."""

    items: list[InboundEmailListItem]
    total: int
    page: int
    page_size: int
    pages: int


class InboundEmailDetailResponse(BaseModel):
    """Detailed inbound email response."""

    id: str
    message_id: str | None
    in_reply_to: str | None
    from_email: str
    from_name: str | None
    to_emails: list[dict[str, Any]]
    cc_emails: list[dict[str, Any]]
    reply_to_email: str | None
    reply_to_name: str | None
    subject: str
    html_body: str | None
    text_body: str | None
    headers: dict[str, Any]
    sent_at_date: str | None
    spam_score: float
    status: str
    webhook_response_code: int | None
    error_message: str | None
    retry_count: int
    received_at: datetime | None
    forwarded_at: datetime | None
    created_at: datetime
    attachments: list[AttachmentPayload] = []

    model_config = ConfigDict(from_attributes=True)
