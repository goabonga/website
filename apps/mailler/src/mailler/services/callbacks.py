# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Status callbacks: telling a client what became of its emails.

A client may register a callback URL and a secret. Each time one of its emails
is sent, delivered, bounced or fails, the service posts a JSON notification to
that URL, signed with the secret, so the application needs no polling.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime

from sqlalchemy import select

from mailler.logging import get_logger
from mailler.models.client import AuthorizedClient
from mailler.models.email import Email, EmailStatus

logger = get_logger(__name__)

# The statuses a client is told about (pending and queued are internal)
NOTIFIED_STATUSES = frozenset(
    {
        EmailStatus.SENT.value,
        EmailStatus.DELIVERED.value,
        EmailStatus.BOUNCED.value,
        EmailStatus.FAILED.value,
    }
)

SIGNATURE_HEADER = "X-Mailler-Signature"
TIMESTAMP_HEADER = "X-Mailler-Timestamp"
EVENT_HEADER = "X-Mailler-Event"
EVENT = "email.status"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Return the signature of a notification: ``sha256=`` + HMAC-SHA256 of ``timestamp.body``."""
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def build_payload(email: Email, status: str, occurred_at: datetime | None = None) -> bytes:
    """Serialize the notification of a status change."""
    payload = {
        "event": EVENT,
        "email_id": str(email.id),
        "client_id": email.client_id,
        "status": status,
        "to_email": email.to_email,
        "provider": email.provider,
        "provider_message_id": email.provider_message_id,
        "error_message": email.error_message,
        "metadata": email.metadata_ or {},
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def notify_status_change(db, email: Email) -> bool:
    """Queue the notification of the current status of an email, if its client wants one.

    This never raises: a notification that cannot be queued (no database, no
    broker) is logged and must not undo or retry the delivery it reports.

    Args:
        db: Synchronous database session.
        email: The email whose status just changed.

    Returns:
        True when a notification was queued.
    """
    if not email.client_id or email.status not in NOTIFIED_STATUSES:
        return False
    try:
        client = db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == email.client_id)
        ).scalar_one_or_none()
        if client is None or not client.callback_url:
            return False

        from mailler.tasks.callbacks import deliver_status_callback

        deliver_status_callback.delay(str(email.id), email.status)
    except Exception as error:
        logger.error(
            "Status callback could not be queued",
            extra={"email_id": str(email.id), "error": str(error)},
        )
        return False
    return True
