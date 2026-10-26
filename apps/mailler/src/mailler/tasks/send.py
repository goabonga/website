# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email sending Celery task."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from mailler.celery import celery_app
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus, ProviderStats
from mailler.services.providers import get_provider

logger = get_logger(__name__)


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

            logger.error(
                "Provider error",
                extra={"email_id": email_id, "error": str(e)},
            )
            return {"status": EmailStatus.FAILED.value, "error": str(e)}
