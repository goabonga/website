# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email sending tasks."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from auth.celery import celery_app
from auth.config import settings

logger = logging.getLogger(__name__)

# Cache for platform tenant sender to avoid DB query on every email
_platform_sender_cache: dict[str, str | None] = {}


def _get_platform_sender() -> tuple[str | None, str | None]:
    """Get the email sender config from the platform tenant settings.

    Uses a simple in-process cache. Returns (from_email, from_name),
    both None if not configured (will fall back to global settings).
    """
    if "from_email" in _platform_sender_cache:
        return _platform_sender_cache.get("from_email"), _platform_sender_cache.get("from_name")

    from_email = None
    from_name = None

    try:
        from sqlalchemy import create_engine, text

        from auth.core.database import get_sync_database_url

        sync_url = get_sync_database_url(settings.database_url)
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT settings FROM tenants WHERE is_platform = true LIMIT 1")
            ).first()
            if row and row[0]:
                tenant_settings = row[0]
                from_email = tenant_settings.get("email_sender_address")
                from_name = tenant_settings.get("email_sender_name")
        engine.dispose()
    except Exception as e:
        logger.warning("Failed to load platform tenant sender: %s", e)

    _platform_sender_cache["from_email"] = from_email
    _platform_sender_cache["from_name"] = from_name
    return from_email, from_name


def invalidate_platform_sender_cache() -> None:
    """Clear the platform sender cache (call after updating settings)."""
    _platform_sender_cache.clear()


def _send_via_smtp(
    to: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    from_email: str | None = None,
    from_name: str | None = None,
) -> dict[str, Any]:
    """Send email via direct SMTP.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body_html: HTML body content.
        body_text: Plain text body content.
        from_email: Sender email (optional, falls back to settings.smtp_from).
        from_name: Sender display name (optional).

    Returns:
        Dict with status and details.

    Raises:
        Exception: If SMTP sending fails.
    """
    logger.info(f"Sending email to {to} via SMTP ({settings.smtp_host}:{settings.smtp_port})")

    sender_addr = from_email or settings.smtp_from
    sender = f"{from_name} <{sender_addr}>" if from_name else sender_addr

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Determine TLS mode
    use_implicit_tls = settings.smtp_tls and settings.smtp_port == 465

    if use_implicit_tls:
        # Implicit TLS (port 465)
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
        ) as smtp:
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(sender_addr, to, msg.as_string())
    else:
        # STARTTLS (port 587) or no TLS
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
        ) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(sender_addr, to, msg.as_string())

    logger.info(f"Email sent successfully to {to} via SMTP")
    return {"status": "sent", "to": to, "subject": subject, "backend": "smtp"}


def _send_via_mailler(
    to: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    from_email: str | None = None,
    from_name: str | None = None,
) -> dict[str, Any]:
    """Send email via mailler service.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body_html: HTML body content.
        body_text: Plain text body content.
        from_email: Sender email (optional, uses mailler default).
        from_name: Sender display name (optional).

    Returns:
        Dict with status and details.

    Raises:
        Exception: If mailler sending fails.
    """
    from auth.services.mailler import get_mailler_client

    logger.info(f"Sending email to {to} via mailler service")

    client = get_mailler_client()
    result = client.send_email(
        to_email=to,
        subject=subject,
        html_content=body_html,
        text_content=body_text or None,
        from_email=from_email,
        from_name=from_name,
        metadata={"source": "auth-service"},
    )

    logger.info(f"Email queued via mailler: id={result.get('id')}, status={result.get('status')}")
    return {
        "status": result.get("status", "queued"),
        "to": to,
        "subject": subject,
        "backend": "mailler",
        "mailler_id": result.get("id"),
        "task_id": result.get("task_id"),
    }


@celery_app.task(name="send_email", bind=True, max_retries=3, ignore_result=True)
def send_email(
    self,
    to: str,
    subject: str,
    body_html: str,
    body_text: str = "",
    from_email: str | None = None,
    from_name: str | None = None,
) -> dict:
    """Send an email asynchronously via Celery.

    Routes to either SMTP or mailler backend based on EMAIL_BACKEND setting.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body_html: HTML body content.
        body_text: Plain text body content.
        from_email: Sender email (optional).
        from_name: Sender display name (optional).

    Returns:
        Dict with status and details.
    """
    # Load platform tenant sender if no explicit sender provided
    if not from_email:
        from_email, from_name = _get_platform_sender()

    backend = settings.email_backend.lower()

    # Use mailler if configured
    if backend == "mailler":
        if not settings.mailler_url:
            logger.warning(
                "Mailler backend selected but MAILLER_URL not configured, falling back to SMTP"
            )
            backend = "smtp"
        else:
            try:
                return _send_via_mailler(to, subject, body_html, body_text, from_email, from_name)
            except Exception as e:
                logger.error(f"Failed to send email to {to} via mailler: {e}")
                # Retry with exponential backoff
                try:
                    self.retry(countdown=60 * (2**self.request.retries))
                except self.MaxRetriesExceededError:
                    logger.error(f"Max retries exceeded for email to {to} via mailler")
                    return {
                        "status": "failed",
                        "to": to,
                        "subject": subject,
                        "backend": "mailler",
                        "error": str(e),
                    }
                raise

    # SMTP backend (default)
    if not settings.smtp_host:
        # Log email to console if SMTP not configured
        logger.warning("SMTP not configured, logging email to console")
        logger.info(f"Email to: {to}, subject: {subject}")
        logger.debug(f"Email body: {body_html}")
        return {"status": "logged", "to": to, "subject": subject, "backend": "console"}

    try:
        return _send_via_smtp(to, subject, body_html, body_text, from_email, from_name)
    except Exception as e:
        logger.error(f"Failed to send email to {to} via SMTP: {e}")
        # Retry with exponential backoff
        try:
            self.retry(countdown=60 * (2**self.request.retries))
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for email to {to} via SMTP")
            return {
                "status": "failed",
                "to": to,
                "subject": subject,
                "backend": "smtp",
                "error": str(e),
            }
        raise
