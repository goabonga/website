# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Receive the webhooks of the Custom Domain Service.

When a client has a webhook configured, the service POSTs a JSON notification to it
on every status change of its domains, so the application does not have to poll.
Every delivery is signed; check the signature on the **raw** request body before
trusting it::

    from custom_domain.client.webhooks import construct_event, WebhookSignatureError

    def handle(request):  # any web framework: you need the raw bytes and the headers
        try:
            event = construct_event(
                request.body,
                request.headers["X-Custom-Domain-Signature"],
                secret=WEBHOOK_SECRET,
            )
        except WebhookSignatureError:
            return 400
        if event.event == "domain.active":
            mark_domain_active(event.domain["domain"])

Answer with any ``2xx`` status once the event is stored; anything else (or no answer)
is retried with an exponential back-off, so handlers must be idempotent: use
``event.id`` to deduplicate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from custom_domain.client.client import CustomDomainError
from custom_domain.webhook_signature import (
    DEFAULT_TOLERANCE_SECONDS,
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    SignatureError,
    verify_signature,
)

__all__ = [
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "SIGNATURE_HEADER",
    "WebhookEvent",
    "WebhookSignatureError",
    "construct_event",
    "verify_webhook_signature",
]

EVENTS = (
    "domain.status_changed",
    "domain.active",
    "domain.failed",
    "domain.deleted",
)


class WebhookSignatureError(CustomDomainError):
    """The signature of a webhook delivery is missing, wrong or too old."""


@dataclass
class WebhookEvent:
    """A verified webhook delivery."""

    id: str
    event: str
    created_at: datetime | None
    domain: dict[str, Any]
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str | None:
        """Status of the domain when the delivery was made."""
        return self.domain.get("status")


def verify_webhook_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
    tolerance_seconds: int | None = DEFAULT_TOLERANCE_SECONDS,
) -> int:
    """Check the signature of a delivery.

    Args:
        body: The raw request body, exactly as received
        signature_header: Value of the ``X-Custom-Domain-Signature`` header
        secret: The client's webhook secret
        tolerance_seconds: Maximum age of the delivery (5 minutes by default);
            ``None`` disables the replay check

    Returns:
        The signing timestamp (Unix seconds)

    Raises:
        WebhookSignatureError: If the signature is missing, malformed, wrong or too old
    """
    try:
        return verify_signature(secret, body, signature_header, tolerance_seconds)
    except SignatureError as error:
        raise WebhookSignatureError(str(error)) from error


def construct_event(
    body: bytes,
    signature_header: str | None,
    secret: str,
    tolerance_seconds: int | None = DEFAULT_TOLERANCE_SECONDS,
) -> WebhookEvent:
    """Verify a delivery and parse it.

    Raises:
        WebhookSignatureError: If the signature does not verify or the body is not a
            valid delivery
    """
    verify_webhook_signature(body, signature_header, secret, tolerance_seconds)
    try:
        document = json.loads(body)
        created_at = document.get("created_at")
        return WebhookEvent(
            id=document["id"],
            event=document["event"],
            created_at=datetime.fromisoformat(created_at) if created_at else None,
            domain=document["domain"],
            data=document.get("data", {}),
        )
    except (ValueError, KeyError, AttributeError, TypeError) as error:
        raise WebhookSignatureError(f"Malformed webhook body: {error}") from error
