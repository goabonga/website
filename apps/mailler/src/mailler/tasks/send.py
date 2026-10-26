# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email sending Celery task."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from mailler.celery import celery_app
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.campaign import EmailCampaign, EmailSend, EmailSendStatus
from mailler.models.email import Email, EmailStatus, ProviderStats
from mailler.services.providers import get_provider
from mailler.services.rendering import convert_percent_syntax, html_template, text_template
from mailler.services.webhook_signature import build_unsubscribe_url

logger = get_logger(__name__)


def _convert_percent_syntax(text: str) -> str:
    """Convert %variable% syntax to Jinja2 {{ variable }} syntax.

    This allows plain text templates to use simpler %var% notation
    while still being processed by Jinja2.

    Args:
        text: Template text with %variable% syntax

    Returns:
        Template text with {{ variable }} syntax
    """
    return convert_percent_syntax(text)


def _update_provider_stats(db, provider: str, status: str) -> None:
    """Update provider statistics.

    Args:
        db: Database session
        provider: Provider name
        status: Email status (sent, delivered, bounced, failed)
    """
    today = date.today()

    # Try to get existing stats record
    stmt = select(ProviderStats).where(
        ProviderStats.date == today,
        ProviderStats.provider == provider,
    )
    stats = db.execute(stmt).scalar_one_or_none()

    if stats is None:
        # Create new stats record
        stats = ProviderStats(date=today, provider=provider)
        db.add(stats)

    # Update counts (handle None when creating new record before flush)
    if status == "sent":
        stats.sent_count = (stats.sent_count or 0) + 1
    elif status == "delivered":
        stats.delivered_count = (stats.delivered_count or 0) + 1
    elif status == "bounced":
        stats.bounced_count = (stats.bounced_count or 0) + 1
    elif status == "failed":
        stats.failed_count = (stats.failed_count or 0) + 1

    db.commit()


def _update_email_send_status(
    db,
    email: Email,
    status: str,
    message_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update EmailSend record status when email is sent (for campaign tracking).

    Args:
        db: Database session
        email: Email record with metadata containing email_send_id
        status: New status (sent, failed)
        message_id: Provider message ID
        error_message: Error message if failed
    """
    if not email.metadata_:
        return

    email_send_id = email.metadata_.get("email_send_id")
    campaign_id = email.metadata_.get("campaign_id")

    if not email_send_id:
        return

    try:
        # Update EmailSend record
        email_send = db.get(EmailSend, uuid.UUID(email_send_id))
        if email_send:
            now = datetime.now(UTC)
            if status == "sent":
                email_send.status = EmailSendStatus.SENT.value
                email_send.sent_at = now
                email_send.message_id = message_id
            elif status == "failed":
                email_send.status = EmailSendStatus.FAILED.value
                email_send.error_message = error_message
            db.commit()

            # Update campaign statistics
            if campaign_id:
                campaign = db.get(EmailCampaign, int(campaign_id))
                if campaign:
                    if status == "sent":
                        campaign.sent_count = (campaign.sent_count or 0) + 1
                    elif status == "failed":
                        campaign.failed_count = (campaign.failed_count or 0) + 1
                    db.commit()

                    logger.info(
                        "Updated campaign stats",
                        extra={
                            "campaign_id": campaign_id,
                            "email_send_id": email_send_id,
                            "new_status": status,
                            "sent_count": campaign.sent_count,
                        },
                    )
    except Exception as e:
        logger.error(
            "Failed to update EmailSend status",
            extra={
                "email_send_id": email_send_id,
                "error": str(e),
            },
        )


@celery_app.task(
    bind=True,
    name="mailler.tasks.send.send_email_task",
    max_retries=settings.send_max_retries,
    default_retry_delay=settings.send_retry_delay,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=settings.send_retry_backoff_max,
    retry_jitter=True,
)
def send_email_task(self, email_id: str) -> dict:
    """Send a single email via the configured provider.

    Args:
        email_id: UUID of the email to send

    Returns:
        Dict with status and optional message ID
    """
    with get_sync_db() as db:
        # Fetch email record
        email = db.get(Email, uuid.UUID(email_id))
        if not email:
            logger.error("Email not found", extra={"email_id": email_id})
            return {"error": "Email not found"}

        # Check if already processed
        if email.status not in [
            EmailStatus.PENDING.value,
            EmailStatus.QUEUED.value,
        ]:
            logger.info(
                "Email already processed",
                extra={"email_id": email_id, "status": email.status},
            )
            return {"status": email.status}

        # Update status to queued
        email.status = EmailStatus.QUEUED.value
        email.queued_at = datetime.now(UTC)
        email.task_id = self.request.id
        db.commit()

        try:
            # Get provider and send
            provider = get_provider(email.provider)
            result = provider.send_email(
                to=email.to_email,
                subject=email.subject,
                html_body=email.html_content,
                plain_body=email.text_content,
                from_name=email.from_name,
                from_email=email.from_email,
                reply_to=email.reply_to,
                email_id=email_id,  # For webhook signature
                metadata=email.metadata_,  # For campaign tracking in webhooks
            )

            if result.success:
                email.status = EmailStatus.SENT.value
                email.sent_at = datetime.now(UTC)
                email.provider_message_id = result.provider_message_id
                db.commit()

                _update_provider_stats(db, email.provider, "sent")
                _update_email_send_status(db, email, "sent", message_id=result.provider_message_id)

                logger.info(
                    "Email sent successfully",
                    extra={
                        "email_id": email_id,
                        "provider": email.provider,
                        "message_id": result.provider_message_id,
                    },
                )
                return {
                    "status": EmailStatus.SENT.value,
                    "message_id": result.provider_message_id,
                }
            else:
                # Update retry count
                email.retry_count += 1
                email.error_message = result.error_message

                # Check if max retries reached
                if email.retry_count >= settings.send_max_retries:
                    email.status = EmailStatus.FAILED.value
                    email.failed_at = datetime.now(UTC)
                    db.commit()
                    _update_provider_stats(db, email.provider, "failed")
                    _update_email_send_status(
                        db, email, "failed", error_message=result.error_message
                    )

                    logger.error(
                        "Email failed after max retries",
                        extra={
                            "email_id": email_id,
                            "provider": email.provider,
                            "error": result.error_message,
                        },
                    )
                    return {
                        "status": EmailStatus.FAILED.value,
                        "error": result.error_message,
                    }

                db.commit()

                logger.warning(
                    "Email send failed, retrying",
                    extra={
                        "email_id": email_id,
                        "provider": email.provider,
                        "retry": email.retry_count,
                        "error": result.error_message,
                    },
                )
                raise Exception(result.error_message)

        except ValueError as e:
            # Provider not configured
            email.status = EmailStatus.FAILED.value
            email.failed_at = datetime.now(UTC)
            email.error_message = str(e)
            db.commit()
            _update_provider_stats(db, email.provider, "failed")
            _update_email_send_status(db, email, "failed", error_message=str(e))

            logger.error(
                "Provider error",
                extra={"email_id": email_id, "error": str(e)},
            )
            return {"status": EmailStatus.FAILED.value, "error": str(e)}


@celery_app.task(
    bind=True,
    name="mailler.tasks.send.send_campaign_task",
    max_retries=0,  # Don't retry the whole campaign, just individual emails
)
def send_campaign_task(self, campaign_id: int) -> dict:
    """Process and send emails for a campaign.

    For each contact in the campaign's group:
    1. Creates an EmailSend record to track the send
    2. Renders the template with contact variables
    3. Creates an Email record
    4. Queues the email for sending

    Respects campaign pause/cancel status - checks before each batch.

    Args:
        campaign_id: ID of the campaign to process

    Returns:
        Dict with statistics about the processing
    """
    from jinja2 import TemplateError
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from mailler.models.campaign import (
        CampaignStatus,
        EmailCampaign,
        EmailSend,
        EmailSendStatus,
    )
    from mailler.models.contact import Contact, ContactGroupMember

    with get_sync_db() as db:
        # Load campaign with relationships
        stmt = (
            select(EmailCampaign)
            .where(EmailCampaign.id == campaign_id)
            .options(
                selectinload(EmailCampaign.template),
                selectinload(EmailCampaign.group),
            )
        )
        campaign = db.execute(stmt).scalar_one_or_none()

        if not campaign:
            logger.error("Campaign not found", extra={"campaign_id": campaign_id})
            return {"error": "Campaign not found"}

        if campaign.status not in [CampaignStatus.SENDING.value]:
            logger.info(
                "Campaign not in sending status, skipping",
                extra={"campaign_id": campaign_id, "status": campaign.status},
            )
            return {"skipped": True, "reason": f"Status is {campaign.status}"}

        if not campaign.template:
            logger.error("Campaign has no template", extra={"campaign_id": campaign_id})
            campaign.status = CampaignStatus.FAILED.value
            db.commit()
            return {"error": "No template"}

        if not campaign.group_id:
            logger.error("Campaign has no group", extra={"campaign_id": campaign_id})
            campaign.status = CampaignStatus.FAILED.value
            db.commit()
            return {"error": "No group"}

        # Get template data: the templates are written by the clients, so they are
        # rendered in a sandbox; the HTML is auto-escaped, the subject and the plain
        # text (where %variable% stands for {{ variable }}) are not
        template = campaign.template
        try:
            html_tpl = html_template(template.html_compiled or "")
            subject_tpl = text_template(campaign.subject_override or template.subject_template)
            plain_text_tpl = (
                text_template(template.plain_text, percent_syntax=True)
                if template.plain_text
                else None
            )
        except TemplateError as e:
            logger.error(
                "Campaign template cannot be compiled",
                extra={"campaign_id": campaign_id, "error": str(e)},
            )
            campaign.status = CampaignStatus.FAILED.value
            db.commit()
            return {"error": "Invalid template"}

        # Determine email settings
        from_email = campaign.from_email or settings.default_from
        from_name = campaign.from_name or settings.default_from_name
        reply_to = campaign.reply_to
        provider = campaign.provider or settings.default_provider

        if not from_email or not provider:
            logger.error(
                "Campaign has no sender or no provider",
                extra={"campaign_id": campaign_id},
            )
            campaign.status = CampaignStatus.FAILED.value
            db.commit()
            return {"error": "No sender or provider"}

        # Get contacts that haven't been sent yet
        # First, get contact IDs already in EmailSend for this campaign
        existing_sends_stmt = select(EmailSend.contact_id).where(
            EmailSend.campaign_id == campaign_id
        )
        existing_contact_ids = {
            row[0] for row in db.execute(existing_sends_stmt).fetchall() if row[0] is not None
        }

        # Get active contacts in the group
        contacts_stmt = (
            select(Contact)
            .join(ContactGroupMember)
            .where(ContactGroupMember.group_id == campaign.group_id)
            .where(Contact.client_id == campaign.client_id)
            .where(Contact.status == "active")
        )
        if existing_contact_ids:
            contacts_stmt = contacts_stmt.where(Contact.id.notin_(existing_contact_ids))
        contacts = db.execute(contacts_stmt).scalars().all()

        logger.info(
            "Processing campaign",
            extra={
                "campaign_id": campaign_id,
                "contacts_to_process": len(contacts),
                "already_sent": len(existing_contact_ids),
            },
        )

        queued_count = 0
        failed_count = 0
        batch_size = settings.campaign_batch_size

        for i, contact in enumerate(contacts):
            # Check if campaign was paused (every batch_size contacts)
            if i > 0 and i % batch_size == 0:
                db.refresh(campaign)
                if campaign.status != CampaignStatus.SENDING.value:
                    logger.info(
                        "Campaign paused or cancelled, stopping",
                        extra={
                            "campaign_id": campaign_id,
                            "status": campaign.status,
                            "processed": i,
                        },
                    )
                    break

            try:
                # Build template context from contact
                context = {
                    "email": contact.email,
                    "first_name": contact.first_name or "",
                    "last_name": contact.last_name or "",
                    "full_name": contact.full_name or "",
                    "unsubscribe_url": build_unsubscribe_url(contact.email, campaign.client_id),
                }
                # Add custom fields
                if contact.custom_fields:
                    context.update(contact.custom_fields)

                # Render templates
                rendered_html = html_tpl.render(**context)
                rendered_subject = subject_tpl.render(**context)
                rendered_plain_text = plain_text_tpl.render(**context) if plain_text_tpl else None

                # Create EmailSend record
                email_send = EmailSend(
                    campaign_id=campaign_id,
                    contact_id=contact.id,
                    recipient_email=contact.email,
                    recipient_name=contact.full_name,
                    status=EmailSendStatus.QUEUED.value,
                    queued_at=datetime.now(UTC),
                )
                db.add(email_send)
                db.flush()  # Get the ID

                # Create Email record
                email = Email(
                    client_id=campaign.client_id,
                    to_email=contact.email,
                    to_name=contact.full_name,
                    from_email=from_email,
                    from_name=from_name,
                    reply_to=reply_to,
                    subject=rendered_subject,
                    html_content=rendered_html,
                    text_content=rendered_plain_text,
                    provider=provider,
                    status=EmailStatus.PENDING.value,
                    metadata_={
                        "campaign_id": campaign_id,
                        "email_send_id": str(email_send.id),
                        "contact_id": str(contact.id),
                    },
                )
                db.add(email)
                db.flush()

                # Update EmailSend with email reference in metadata
                email_send.metadata_ = {"email_id": str(email.id)}

                db.commit()

                # Queue the email task
                send_email_task.delay(str(email.id))
                queued_count += 1

            except Exception as e:
                db.rollback()
                logger.error(
                    "Failed to process contact",
                    extra={
                        "campaign_id": campaign_id,
                        "contact_id": str(contact.id),
                        "error": str(e),
                    },
                )
                failed_count += 1

        # Update campaign statistics
        db.refresh(campaign)

        # Count sent/failed from EmailSend
        sent_count = (
            db.execute(
                select(func.count(EmailSend.id))
                .where(EmailSend.campaign_id == campaign_id)
                .where(
                    EmailSend.status.in_(
                        [
                            EmailSendStatus.SENT.value,
                            EmailSendStatus.DELIVERED.value,
                            EmailSendStatus.OPENED.value,
                            EmailSendStatus.CLICKED.value,
                        ]
                    )
                )
            ).scalar()
            or 0
        )

        total_queued = (
            db.execute(
                select(func.count(EmailSend.id)).where(EmailSend.campaign_id == campaign_id)
            ).scalar()
            or 0
        )

        # Check if all emails are processed
        if (
            total_queued >= campaign.total_recipients
            and campaign.status == CampaignStatus.SENDING.value
        ):
            campaign.status = CampaignStatus.COMPLETED.value
            campaign.completed_at = datetime.now(UTC)
            logger.info(
                "Campaign completed",
                extra={"campaign_id": campaign_id, "total_sent": total_queued},
            )

        campaign.sent_count = sent_count
        db.commit()

        return {
            "campaign_id": campaign_id,
            "queued": queued_count,
            "failed": failed_count,
            "total_processed": queued_count + failed_count,
        }
