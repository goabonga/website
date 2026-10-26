# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Delivery of the status callbacks to the clients."""

import time
import uuid

import httpx
from sqlalchemy import select

from mailler.celery import celery_app
from mailler.config import settings
from mailler.database import get_sync_db
from mailler.logging import get_logger
from mailler.models.client import AuthorizedClient
from mailler.models.email import Email
from mailler.services.callbacks import (
    EVENT,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_payload,
    sign,
)

logger = get_logger(__name__)


class CallbackFailed(Exception):
    """The client's endpoint did not accept the notification (it is delivered again later)."""


@celery_app.task(
    bind=True,
    name="mailler.tasks.callbacks.deliver_status_callback",
    max_retries=settings.callback_max_retries,
    autoretry_for=(CallbackFailed,),
    retry_backoff=settings.callback_retry_delay,
    retry_backoff_max=3600,
    retry_jitter=True,
)
def deliver_status_callback(self, email_id: str, status: str) -> dict:
    """Post the notification of a status change to the callback URL of the email's client.

    A 2xx answer is a success; anything else (including a network error) is
    delivered again with an exponential backoff, up to ``CALLBACK_MAX_RETRIES``
    times, after which the notification is dropped and logged.

    Args:
        email_id: UUID of the email.
        status: Status the email just reached.

    Returns:
        Dict with the outcome.
    """
    with get_sync_db() as db:
        email = db.get(Email, uuid.UUID(email_id))
        if email is None or not email.client_id:
            return {"skipped": "email not found"}
        client = db.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == email.client_id)
        ).scalar_one_or_none()
        if client is None or not client.callback_url or not client.callback_secret:
            return {"skipped": "no callback configured"}
        url, secret = client.callback_url, client.callback_secret
        body = build_payload(email, status)
        client_id = email.client_id

    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(secret, timestamp, body),
        EVENT_HEADER: EVENT,
    }
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=settings.callback_timeout)
    except httpx.HTTPError as error:
        logger.warning(
            "Status callback failed",
            extra={"email_id": email_id, "client_id": client_id, "error": str(error)},
        )
        raise CallbackFailed(str(error)) from error

    if not response.is_success:
        logger.warning(
            "Status callback refused",
            extra={
                "email_id": email_id,
                "client_id": client_id,
                "http_status": response.status_code,
            },
        )
        raise CallbackFailed(f"HTTP {response.status_code}")

    logger.info(
        "Status callback delivered",
        extra={"email_id": email_id, "client_id": client_id, "status": status},
    )
    return {"delivered": True, "http_status": response.status_code}
