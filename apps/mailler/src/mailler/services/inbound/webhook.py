# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhook delivery for inbound emails."""

import hashlib
import hmac

import httpx

from mailler.config import settings
from mailler.logging import get_logger
from mailler.models.inbound import InboundAttachment, InboundEmail
from mailler.schemas.inbound import (
    AttachmentPayload,
    InboundEmailPayload,
    InboundWebhookPayload,
    Mailbox,
)
from mailler.services.inbound.parser import html_to_markdown

logger = get_logger(__name__)


def build_brevo_payload(
    inbound_email: InboundEmail,
    attachments: list[InboundAttachment],
) -> InboundWebhookPayload:
    """Build a Brevo-compatible webhook payload from an InboundEmail.

    Args:
        inbound_email: InboundEmail DB record.
        attachments: Associated InboundAttachment records.

    Returns:
        InboundWebhookPayload ready for JSON serialization.
    """
    # Build From mailbox
    from_mailbox = Mailbox(
        Address=inbound_email.from_email,
        Name=inbound_email.from_name,
    )

    # Build To mailboxes
    to_mailboxes = [
        Mailbox(Address=addr.get("Address", ""), Name=addr.get("Name"))
        for addr in (inbound_email.to_emails or [])
    ]

    # Build Cc mailboxes
    cc_mailboxes = [
        Mailbox(Address=addr.get("Address", ""), Name=addr.get("Name"))
        for addr in (inbound_email.cc_emails or [])
    ]

    # Build ReplyTo
    reply_to = None
    if inbound_email.reply_to_email:
        reply_to = Mailbox(
            Address=inbound_email.reply_to_email,
            Name=inbound_email.reply_to_name,
        )

    # Build attachments
    attachment_payloads = [
        AttachmentPayload(
            Name=att.filename,
            ContentType=att.content_type,
            ContentLength=att.content_length,
            ContentID=att.content_id,
            DownloadToken=str(att.download_token),
        )
        for att in attachments
    ]

    # Extract markdown from HTML if available
    markdown_message = ""
    if inbound_email.html_body:
        markdown_message = html_to_markdown(inbound_email.html_body)
    elif inbound_email.text_body:
        markdown_message = inbound_email.text_body

    # Build headers dict (flatten to string values)
    headers = {}
    for key, value in (inbound_email.headers or {}).items():
        headers[key] = str(value) if value else ""

    email_payload = InboundEmailPayload(
        Uuid=[str(inbound_email.id)],
        MessageId=inbound_email.message_id or "",
        InReplyTo=inbound_email.in_reply_to,
        From=from_mailbox,
        To=to_mailboxes,
        Recipients=to_mailboxes,  # Same as To for direct IMAP
        Cc=cc_mailboxes,
        ReplyTo=reply_to,
        SentAtDate=inbound_email.sent_at_date or "",
        Subject=inbound_email.subject,
        RawHtmlBody=inbound_email.html_body,
        RawTextBody=inbound_email.text_body,
        ExtractedMarkdownMessage=markdown_message,
        ExtractedMarkdownSignature=None,
        SpamScore=inbound_email.spam_score,
        Attachments=attachment_payloads,
        Headers=headers,
    )

    return InboundWebhookPayload(items=[email_payload])


def _generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload.

    Args:
        payload_bytes: JSON payload bytes.
        secret: HMAC secret key.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def deliver_webhook(payload: InboundWebhookPayload) -> tuple[int, bool]:
    """Deliver a webhook payload to the configured target URL.

    Args:
        payload: InboundWebhookPayload to deliver.

    Returns:
        Tuple of (http_status_code, success).
    """
    url = settings.inbound_webhook_url
    if not url:
        logger.error("No inbound webhook URL configured")
        return (0, False)

    payload_json = payload.model_dump_json()
    payload_bytes = payload_json.encode("utf-8")

    headers = {"Content-Type": "application/json"}

    # Add HMAC signature if secret is configured
    if settings.inbound_webhook_secret:
        signature = _generate_signature(payload_bytes, settings.inbound_webhook_secret)
        headers["X-Webhook-Signature"] = signature

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, content=payload_bytes, headers=headers)

        success = 200 <= response.status_code < 300

        if success:
            logger.info(
                "Webhook delivered",
                extra={"url": url, "status_code": response.status_code},
            )
        else:
            logger.warning(
                "Webhook delivery returned non-2xx",
                extra={"url": url, "status_code": response.status_code},
            )

        return (response.status_code, success)

    except httpx.TimeoutException:
        logger.error("Webhook delivery timed out", extra={"url": url})
        return (0, False)
    except httpx.RequestError as e:
        logger.error(
            "Webhook delivery failed",
            extra={"url": url, "error": str(e)},
        )
        return (0, False)
