# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhook endpoints for receiving provider callbacks.

This module handles webhook events from email providers (Brevo, SendGrid, etc.)
and updates the email status and campaign statistics accordingly.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from mailler.auth.dependencies import AuthContext, require_scopes
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.campaign import EmailCampaign, EmailSend, EmailSendStatus
from mailler.models.contact import Contact
from mailler.models.email import Email, EmailStatus
from mailler.services.webhook_signature import parse_mailin_custom, verify_webhook_signature

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _update_email_status(
    email_id: str,
    new_status: EmailStatus,
    error_message: str | None = None,
    provider_message_id: str | None = None,
) -> Email | None:
    """Update email status in database.

    Args:
        email_id: UUID of the email record.
        new_status: New status to set.
        error_message: Error message for bounces/failures.
        provider_message_id: Provider's message ID.

    Returns:
        Updated Email object or None if not found.
    """
    try:
        with get_sync_db() as db:
            email = db.get(Email, email_id)
            if not email:
                logger.warning("Email not found for webhook | email_id=%s", email_id)
                return None

            old_status = email.status
            email.status = new_status.value

            now = datetime.now(UTC)
            if new_status == EmailStatus.DELIVERED:
                email.delivered_at = now
            elif new_status == EmailStatus.BOUNCED:
                email.bounced_at = now
                email.error_message = error_message
            elif new_status == EmailStatus.FAILED:
                email.failed_at = now
                email.error_message = error_message

            if provider_message_id and not email.provider_message_id:
                email.provider_message_id = provider_message_id

            db.commit()
            db.refresh(email)

            logger.info(
                "Email status updated | email_id=%s old=%s new=%s",
                email_id,
                old_status,
                new_status.value,
            )
            return email

    except Exception as e:
        logger.error("Failed to update email status: %s", e)
        return None


def _update_campaign_stats(
    recipient_email: str,
    campaign_id: int | None,
    event_type: str,
    error_message: str | None = None,
) -> bool:
    """Update EmailSend and EmailCampaign stats from webhook event.

    Args:
        recipient_email: The recipient email address.
        campaign_id: Campaign ID for targeting.
        event_type: Event type (delivery, bounce, complaint).
        error_message: Error message for bounces.

    Returns:
        True if any records were updated.
    """
    if not campaign_id:
        return False

    try:
        with get_sync_db() as db:
            # Find EmailSend record
            query = select(EmailSend).where(
                EmailSend.recipient_email == recipient_email,
                EmailSend.campaign_id == campaign_id,
            )
            email_send = db.execute(query).scalar_one_or_none()

            if not email_send:
                logger.warning(
                    "EmailSend not found for webhook | email=%s campaign_id=%s",
                    recipient_email,
                    campaign_id,
                )
                return False

            # Get campaign
            campaign = db.get(EmailCampaign, campaign_id)
            if not campaign:
                logger.warning("Campaign not found | campaign_id=%s", campaign_id)
                return False

            now = datetime.now(UTC)
            old_status = email_send.status

            if event_type == "delivery":
                # Only update if currently SENT
                if email_send.status == EmailSendStatus.SENT.value:
                    email_send.status = EmailSendStatus.DELIVERED.value
                    email_send.delivered_at = now
                    campaign.delivered_count = (campaign.delivered_count or 0) + 1
                    logger.info(
                        "Updated EmailSend to delivered | campaign_id=%d email=%s delivered_count=%d",
                        campaign_id,
                        recipient_email,
                        campaign.delivered_count,
                    )

            elif event_type == "bounce":
                # Handle bounces
                if email_send.status in [
                    EmailSendStatus.SENT.value,
                    EmailSendStatus.DELIVERED.value,
                ]:
                    was_delivered = email_send.status == EmailSendStatus.DELIVERED.value
                    email_send.status = EmailSendStatus.BOUNCED.value
                    email_send.bounced_at = now
                    email_send.error_message = error_message
                    campaign.bounced_count = (campaign.bounced_count or 0) + 1
                    # Decrement delivered if was previously delivered
                    if was_delivered and campaign.delivered_count > 0:
                        campaign.delivered_count -= 1

                    # Mark contact as bounced for hard bounces
                    if email_send.contact_id:
                        contact = db.get(Contact, email_send.contact_id)
                        if contact and contact.status == "active":
                            contact.status = "bounced"
                            logger.info(
                                "Marked contact as bounced | contact_id=%s",
                                email_send.contact_id,
                            )

                    logger.info(
                        "Updated EmailSend to bounced | campaign_id=%d email=%s bounced_count=%d",
                        campaign_id,
                        recipient_email,
                        campaign.bounced_count,
                    )

            elif event_type == "complaint":
                if email_send.status in [
                    EmailSendStatus.SENT.value,
                    EmailSendStatus.DELIVERED.value,
                ]:
                    was_delivered = email_send.status == EmailSendStatus.DELIVERED.value
                    email_send.status = EmailSendStatus.COMPLAINED.value
                    email_send.error_message = error_message
                    campaign.complained_count = (campaign.complained_count or 0) + 1
                    if was_delivered and campaign.delivered_count > 0:
                        campaign.delivered_count -= 1

                    # Mark contact as complained
                    if email_send.contact_id:
                        contact = db.get(Contact, email_send.contact_id)
                        if contact and contact.status == "active":
                            contact.status = "complained"
                            logger.info(
                                "Marked contact as complained | contact_id=%s",
                                email_send.contact_id,
                            )

                    logger.info(
                        "Updated EmailSend to complained | campaign_id=%d email=%s complained_count=%d",
                        campaign_id,
                        recipient_email,
                        campaign.complained_count,
                    )

            elif event_type == "open":
                if email_send.status in [
                    EmailSendStatus.DELIVERED.value,
                    EmailSendStatus.OPENED.value,
                    EmailSendStatus.CLICKED.value,
                ]:
                    if email_send.status == EmailSendStatus.DELIVERED.value:
                        email_send.status = EmailSendStatus.OPENED.value
                        campaign.opened_count = (campaign.opened_count or 0) + 1
                    if not email_send.opened_at:
                        email_send.opened_at = now
                    logger.info(
                        "Updated EmailSend to opened | campaign_id=%d email=%s opened_count=%d",
                        campaign_id,
                        recipient_email,
                        campaign.opened_count,
                    )

            elif event_type == "click" and email_send.status in [
                EmailSendStatus.DELIVERED.value,
                EmailSendStatus.OPENED.value,
                EmailSendStatus.CLICKED.value,
            ]:
                # Track open if not already
                if not email_send.opened_at:
                    email_send.opened_at = now
                    if email_send.status == EmailSendStatus.DELIVERED.value:
                        campaign.opened_count = (campaign.opened_count or 0) + 1
                # Track click
                if email_send.status != EmailSendStatus.CLICKED.value:
                    email_send.status = EmailSendStatus.CLICKED.value
                    campaign.clicked_count = (campaign.clicked_count or 0) + 1
                if not email_send.clicked_at:
                    email_send.clicked_at = now
                logger.info(
                    "Updated EmailSend to clicked | campaign_id=%d email=%s clicked_count=%d",
                    campaign_id,
                    recipient_email,
                    campaign.clicked_count,
                )

            db.commit()
            return old_status != email_send.status

    except Exception as e:
        logger.error(
            "Failed to update campaign stats | campaign_id=%s email=%s error=%s",
            campaign_id,
            recipient_email,
            e,
        )
        return False


@router.post("/brevo")
async def brevo_webhook(
    request: Request,
    _auth: AuthContext = Depends(require_scopes("mailler:webhooks")),
) -> Response:
    """Handle Brevo webhook events.

    Receives raw webhook events from Brevo (via webhooks service),
    verifies the signature, updates email status, and forwards
    relevant events to internal API for campaign tracking.
    """
    try:
        body = await request.body()
        if not body:
            return Response(status_code=200)

        event = json.loads(body)

        # Extract common fields
        event_type = event.get("event", "").lower()
        email_address = event.get("email", "").lower()
        if not email_address:
            logger.warning("Brevo webhook missing email field")
            return Response(status_code=200)

        # Parse X-Mailin-custom header
        custom_header = event.get("X-Mailin-custom", "")
        mailin_data = parse_mailin_custom(custom_header)
        email_id = mailin_data.get("email_id")
        signature = mailin_data.get("signature")
        campaign_id = mailin_data.get("campaign_id")

        logger.debug(
            "Brevo webhook received | event=%s email=%s email_id=%s campaign_id=%s",
            event_type,
            email_address,
            email_id,
            campaign_id,
        )

        # Verify signature
        if settings.webhook_hmac_secret:
            if not email_id or not signature:
                logger.warning("Missing email_id or signature in Brevo webhook")
                raise HTTPException(status_code=401, detail="Missing signature")

            if not verify_webhook_signature(email_id, email_address, signature):
                logger.warning("Invalid signature in Brevo webhook")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Process event and update email status
        if event_type == "delivered":
            if email_id:
                _update_email_status(email_id, EmailStatus.DELIVERED)

            # Update campaign stats directly
            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="delivery",
                )

        elif event_type == "hard_bounce":
            reason = event.get("reason", "Hard bounce")
            if email_id:
                _update_email_status(email_id, EmailStatus.BOUNCED, error_message=reason)

            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="bounce",
                    error_message=f"Hard bounce: {reason}",
                )

        elif event_type == "soft_bounce":
            reason = event.get("reason", "Soft bounce")

            # Some soft bounces are actually permanent (domain issues)
            permanent_indicators = ["mx", "domain", "invalid", "not exist", "unknown"]
            is_permanent = any(indicator in reason.lower() for indicator in permanent_indicators)

            if is_permanent:
                # Treat as hard bounce
                logger.info(
                    "Treating soft bounce as hard bounce | email_id=%s reason=%s",
                    email_id,
                    reason,
                )
                if email_id:
                    _update_email_status(
                        email_id,
                        EmailStatus.BOUNCED,
                        error_message=f"Soft bounce (permanent): {reason}",
                    )
                if campaign_id:
                    _update_campaign_stats(
                        recipient_email=email_address,
                        campaign_id=int(campaign_id),
                        event_type="bounce",
                        error_message=f"Soft bounce (permanent): {reason}",
                    )
            else:
                # Temporary soft bounce - provider may retry
                if email_id:
                    logger.info("Soft bounce for email_id=%s: %s", email_id, reason)
                # Don't update campaign stats for temporary soft bounces

        elif event_type in ("blocked", "invalid"):
            reason = event.get("reason") or event_type
            if email_id:
                _update_email_status(email_id, EmailStatus.BOUNCED, error_message=reason)

            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="bounce",
                    error_message=f"{event_type.title()}: {reason}",
                )

        elif event_type == "complaint":
            if email_id:
                _update_email_status(email_id, EmailStatus.BOUNCED, error_message="Spam complaint")

            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="complaint",
                    error_message="Spam complaint",
                )

        elif event_type in ("unsubscribe", "unsubscribed"):
            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="complaint",
                    error_message="Unsubscribed",
                )

        elif event_type in ("open", "unique_opened"):
            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="open",
                )

        elif event_type == "click":
            if campaign_id:
                _update_campaign_stats(
                    recipient_email=email_address,
                    campaign_id=int(campaign_id),
                    event_type="click",
                )

        elif event_type == "request":
            # Request event is just a send confirmation, already handled
            logger.debug(
                "Brevo request event | email=%s email_id=%s",
                email_address,
                email_id,
            )

        else:
            logger.debug("Unhandled Brevo event type: %s", event_type)

        return Response(status_code=200)

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in Brevo webhook: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Error processing Brevo webhook: %s", e)
        raise HTTPException(status_code=500, detail="Internal error")
