# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Inbound email processing Celery tasks."""

import contextlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

from mailler.celery import celery_app
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.inbound import InboundAttachment, InboundEmail, InboundStatus
from mailler.services.inbound.imap_client import (
    connect,
    ensure_folder_exists,
    fetch_unseen_emails,
    move_to_folder,
)
from mailler.services.inbound.parser import ParsedEmail, parse_email_bytes
from mailler.services.inbound.webhook import build_brevo_payload, deliver_webhook

logger = get_logger(__name__)


def _save_attachment(
    attachment_content: bytes,
    filename: str,
    email_id: uuid.UUID,
) -> str:
    """Save attachment content to filesystem.

    Args:
        attachment_content: Raw attachment bytes.
        filename: Original filename.
        email_id: Parent inbound email UUID.

    Returns:
        Absolute file path where attachment was saved.
    """
    base_dir = Path(settings.inbound_attachments_dir)
    email_dir = base_dir / str(email_id)
    email_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename (keep only alphanumeric, dots, hyphens, underscores)
    safe_name = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
    if not safe_name:
        safe_name = "attachment"

    file_path = email_dir / safe_name

    # Handle duplicate filenames
    counter = 1
    original_path = file_path
    while file_path.exists():
        stem = original_path.stem
        suffix = original_path.suffix
        file_path = email_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    file_path.write_bytes(attachment_content)
    return str(file_path)


def _store_inbound_email(
    parsed: ParsedEmail,
    imap_uid: str,
) -> tuple[InboundEmail, list[InboundAttachment]]:
    """Store a parsed email and its attachments in the database.

    Args:
        parsed: ParsedEmail from the parser.
        imap_uid: IMAP UID for reference.

    Returns:
        Tuple of (InboundEmail, list of InboundAttachment).
    """
    with get_sync_db() as db:
        # Check for duplicate by message_id
        if parsed.message_id:
            existing = db.execute(
                select(InboundEmail).where(InboundEmail.message_id == parsed.message_id)
            ).scalar_one_or_none()
            if existing:
                logger.info(
                    "Duplicate inbound email, skipping",
                    extra={"message_id": parsed.message_id},
                )
                attachments = (
                    db.execute(
                        select(InboundAttachment).where(
                            InboundAttachment.inbound_email_id == existing.id
                        )
                    )
                    .scalars()
                    .all()
                )
                return (existing, list(attachments))

        # Create InboundEmail record
        inbound = InboundEmail(
            message_id=parsed.message_id or None,
            in_reply_to=parsed.in_reply_to,
            from_email=parsed.from_email,
            from_name=parsed.from_name,
            to_emails=parsed.to,
            cc_emails=parsed.cc,
            reply_to_email=parsed.reply_to_email,
            reply_to_name=parsed.reply_to_name,
            subject=parsed.subject,
            html_body=parsed.html_body,
            text_body=parsed.text_body,
            headers=parsed.headers,
            sent_at_date=parsed.sent_at_date,
            status=InboundStatus.RECEIVED.value,
            imap_uid=imap_uid,
            received_at=datetime.now(UTC),
        )
        db.add(inbound)
        db.flush()  # Get the ID

        # Save and store attachments
        attachment_records: list[InboundAttachment] = []
        ttl = settings.inbound_attachment_ttl
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

        for att in parsed.attachments:
            file_path = _save_attachment(att.content, att.filename, inbound.id)

            attachment_record = InboundAttachment(
                inbound_email_id=inbound.id,
                filename=att.filename,
                content_type=att.content_type,
                content_length=len(att.content),
                content_id=att.content_id,
                file_path=file_path,
                expires_at=expires_at,
            )
            db.add(attachment_record)
            attachment_records.append(attachment_record)

        db.commit()

        # Refresh to get generated values
        db.refresh(inbound)
        for record in attachment_records:
            db.refresh(record)

        logger.info(
            "Stored inbound email",
            extra={
                "inbound_id": str(inbound.id),
                "from": inbound.from_email,
                "subject": inbound.subject,
                "attachments": len(attachment_records),
            },
        )

        return (inbound, attachment_records)


@celery_app.task(name="mailler.tasks.inbound.poll_inbound_emails")
def poll_inbound_emails() -> dict:
    """Poll IMAP for new inbound emails and forward via webhook.

    Connects to Protonmail Bridge IMAP, fetches unseen emails,
    parses them, stores in DB, builds Brevo-compatible payloads,
    and delivers via HTTP POST to the configured webhook URL.

    Successfully processed emails are moved to the configured folder.

    Returns:
        Dict with processing statistics.
    """
    if not settings.inbound_enabled:
        return {"skipped": True, "reason": "inbound disabled"}

    if not settings.inbound_webhook_url:
        logger.warning("Inbound enabled but no webhook URL configured")
        return {"skipped": True, "reason": "no webhook URL"}

    if not (
        settings.protonmail_host and settings.inbound_imap_port and settings.inbound_attachments_dir
    ):
        logger.warning("Inbound enabled but the mailbox or the attachments directory is not set")
        return {"skipped": True, "reason": "mailbox not configured"}

    processed = 0
    forwarded = 0
    failed = 0
    imap = None

    try:
        imap = connect()
        folder = settings.inbound_processed_folder
        ensure_folder_exists(imap, folder)

        emails = fetch_unseen_emails(imap)

        if not emails:
            return {"processed": 0, "forwarded": 0, "failed": 0}

        for uid, raw_bytes in emails:
            processed += 1

            try:
                # Parse email
                parsed = parse_email_bytes(raw_bytes)

                # Store in DB
                inbound_email, attachments = _store_inbound_email(parsed, uid)

                # Skip if already forwarded (duplicate)
                if inbound_email.status == InboundStatus.FORWARDED.value:
                    logger.debug(
                        "Email already forwarded, moving to folder",
                        extra={"uid": uid},
                    )
                    move_to_folder(imap, uid, folder)
                    continue

                # Build and deliver webhook
                payload = build_brevo_payload(inbound_email, attachments)
                status_code, success = deliver_webhook(payload)

                # Update DB record
                with get_sync_db() as db:
                    email_record = db.get(InboundEmail, inbound_email.id)
                    if email_record:
                        email_record.webhook_response_code = status_code
                        if success:
                            email_record.status = InboundStatus.FORWARDED.value
                            email_record.forwarded_at = datetime.now(UTC)
                            forwarded += 1
                        else:
                            email_record.status = InboundStatus.FAILED.value
                            email_record.error_message = f"Webhook returned status {status_code}"
                            email_record.retry_count += 1
                            failed += 1
                        db.commit()

                # Move to processed folder on success
                if success:
                    move_to_folder(imap, uid, folder)

            except Exception as e:
                failed += 1
                logger.error(
                    "Failed to process inbound email",
                    extra={"uid": uid, "error": str(e)},
                )

    except Exception as e:
        logger.error("IMAP polling failed", extra={"error": str(e)})
        return {
            "error": str(e),
            "processed": processed,
            "forwarded": forwarded,
            "failed": failed,
        }
    finally:
        if imap:  # pragma: no branch
            with contextlib.suppress(Exception):
                imap.logout()

    logger.info(
        "Inbound polling complete",
        extra={"processed": processed, "forwarded": forwarded, "failed": failed},
    )

    return {"processed": processed, "forwarded": forwarded, "failed": failed}


@celery_app.task(name="mailler.tasks.inbound.retry_failed_inbound")
def retry_failed_inbound(max_retries: int = 3) -> dict:
    """Retry forwarding failed inbound emails.

    Finds InboundEmail records with status=FAILED and retry_count < max_retries,
    rebuilds the webhook payload, and attempts delivery again.

    Args:
        max_retries: Maximum number of retry attempts.

    Returns:
        Dict with retry statistics.
    """
    if not settings.inbound_enabled or not settings.inbound_webhook_url:
        return {"skipped": True}

    retried = 0
    succeeded = 0

    with get_sync_db() as db:
        stmt = (
            select(InboundEmail)
            .where(
                InboundEmail.status == InboundStatus.FAILED.value,
                InboundEmail.retry_count < max_retries,
            )
            .limit(20)
        )
        failed_emails = db.execute(stmt).scalars().all()

        for inbound_email in failed_emails:
            retried += 1

            # Load attachments
            att_stmt = select(InboundAttachment).where(
                InboundAttachment.inbound_email_id == inbound_email.id
            )
            attachments = list(db.execute(att_stmt).scalars().all())

            # Build and deliver
            payload = build_brevo_payload(inbound_email, attachments)
            status_code, success = deliver_webhook(payload)

            inbound_email.webhook_response_code = status_code
            inbound_email.retry_count += 1

            if success:
                inbound_email.status = InboundStatus.FORWARDED.value
                inbound_email.forwarded_at = datetime.now(UTC)
                inbound_email.error_message = None
                succeeded += 1
            else:
                inbound_email.error_message = (
                    f"Retry {inbound_email.retry_count}: webhook returned {status_code}"
                )

            db.commit()

    logger.info(
        "Retry failed inbound complete",
        extra={"retried": retried, "succeeded": succeeded},
    )

    return {"retried": retried, "succeeded": succeeded}


@celery_app.task(name="mailler.tasks.inbound.cleanup_expired_attachments")
def cleanup_expired_attachments() -> dict:
    """Delete expired attachment files and DB records.

    Removes attachments that have passed their expiration time (TTL).

    Returns:
        Dict with cleanup statistics.
    """
    now = datetime.now(UTC)
    deleted_files = 0
    deleted_records = 0

    with get_sync_db() as db:
        # Find expired attachments
        stmt = select(InboundAttachment).where(InboundAttachment.expires_at <= now)
        expired = db.execute(stmt).scalars().all()

        for att in expired:
            # Delete file from filesystem
            try:
                if os.path.exists(att.file_path):
                    os.remove(att.file_path)
                    deleted_files += 1

                    # Try to remove empty parent directory
                    parent = os.path.dirname(att.file_path)
                    if os.path.isdir(parent) and not os.listdir(parent):
                        os.rmdir(parent)
            except OSError as e:
                logger.warning(
                    "Failed to delete attachment file",
                    extra={"file_path": att.file_path, "error": str(e)},
                )

        # Delete expired records from DB
        if expired:
            delete_stmt = delete(InboundAttachment).where(InboundAttachment.expires_at <= now)
            result = db.execute(delete_stmt)
            deleted_records = getattr(result, "rowcount", 0) or 0
            db.commit()

    if deleted_records > 0:
        logger.info(
            "Cleaned up expired attachments",
            extra={"deleted_files": deleted_files, "deleted_records": deleted_records},
        )

    return {"deleted_files": deleted_files, "deleted_records": deleted_records}
