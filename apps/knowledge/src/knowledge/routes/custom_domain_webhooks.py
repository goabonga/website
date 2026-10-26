# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Receiver of the status webhooks of the custom-domain service.

The service posts ``domain.status_changed``, ``domain.active``, ``domain.failed`` and
``domain.deleted`` to the URL registered on the authorized client of this application,
signed with the shared secret. The receiver:

* refuses everything while ``CUSTOM_DOMAIN_WEBHOOK_SECRET`` is empty (``503``);
* verifies ``X-Custom-Domain-Signature`` (``t=<unix time>,v1=<hex>``, the HMAC-SHA256 of
  ``<t>.<raw body>``) in constant time, on the raw body, and refuses a timestamp that is too
  far from now: a captured request cannot be played back later;
* processes a delivery once (the delivery id is recorded) and only records it after the
  change is committed, so a failed delivery is retried by the service;
* applies the status of the domain snapshot of the request to the workspace, which is
  idempotent and tolerates deliveries out of order.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.config import get_settings
from knowledge.database import async_session_factory
from knowledge.models import Organization
from knowledge.services import event_dedupe
from knowledge.services.custom_domain import apply_status, clear_domain

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

SIGNATURE_HEADER = "X-Custom-Domain-Signature"
DELIVERY_HEADER = "X-Custom-Domain-Delivery"
EVENT_NAMESPACE = "custom-domain"
STATUS_EVENTS = frozenset({"domain.status_changed", "domain.active", "domain.failed"})


class SignatureError(ValueError):
    """The signature header is missing, malformed, wrong or too old."""


def verify_signature(
    secret: str,
    body: bytes,
    header: str | None,
    tolerance: int,
    now: float | None = None,
) -> int:
    """Check the signature header of a delivery against its raw body.

    Args:
        secret: The webhook secret of the client.
        body: The request body exactly as received.
        header: Value of ``X-Custom-Domain-Signature``.
        tolerance: Maximum difference, in seconds, between the signed time and now.
        now: Current time (for the tests).

    Returns:
        The signed timestamp.

    Raises:
        SignatureError: If the header is missing or malformed, no signature matches, or the
            timestamp is outside the tolerance.
    """
    if not header:
        raise SignatureError("Missing signature")

    timestamp: int | None = None
    candidates: list[str] = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as error:
                raise SignatureError("Malformed signature timestamp") from error
        elif key == "v1":
            candidates.append(value)
    if timestamp is None or not candidates:
        raise SignatureError("Malformed signature")

    message = str(timestamp).encode() + b"." + body
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    # A header may carry several signatures while the secret is being rotated
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise SignatureError("Invalid signature")

    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        raise SignatureError("Timestamp outside the tolerance")
    return timestamp


async def _find_organization(db: AsyncSession, snapshot: dict[str, Any]) -> Organization | None:
    """Find the workspace a domain snapshot belongs to: by service id, else by name and owner."""
    domain_id = str(snapshot.get("id") or "")
    if domain_id:
        result = await db.execute(
            select(Organization).where(Organization.custom_domain_service_id == domain_id)
        )
        organization = result.scalar_one_or_none()
        if organization:
            return organization

    # A domain registered before the id was recorded: the owner id is the workspace id
    name = str(snapshot.get("domain") or "").lower()
    owner_id = str(snapshot.get("owner_id") or "")
    if not name or not owner_id:
        return None
    result = await db.execute(
        select(Organization).where(
            Organization.id == owner_id,
            Organization.custom_domain == name,
        )
    )
    organization = result.scalar_one_or_none()
    if organization and not organization.custom_domain_service_id and domain_id:
        organization.custom_domain_service_id = domain_id
    return organization


def _moment(created_at: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None


async def apply_event(db: AsyncSession, event: dict[str, Any]) -> str:
    """Apply a verified event to the workspace it concerns.

    Returns:
        What was done: ``updated``, ``cleared``, ``unknown`` (no such workspace, e.g. the
        customer removed the domain meanwhile) or ``ignored``.
    """
    name = event.get("event")
    snapshot = event.get("domain") or {}
    if not isinstance(snapshot, dict):
        return "ignored"

    if name == "domain.deleted":
        # The service finished removing the domain: drop it if it is still ours
        organization = await _find_organization(db, snapshot)
        if organization is None:
            return "unknown"
        if organization.custom_domain_service_id == str(snapshot.get("id")):
            clear_domain(organization)
            return "cleared"
        return "ignored"

    if name not in STATUS_EVENTS:
        return "ignored"

    organization = await _find_organization(db, snapshot)
    if organization is None:
        return "unknown"
    applied = apply_status(
        organization,
        snapshot.get("status"),
        error=snapshot.get("error"),
        when=_moment(event.get("created_at")),
    )
    return "updated" if applied else "ignored"


@router.post("/custom-domain", status_code=status.HTTP_200_OK)
async def handle_custom_domain_webhook(request: Request) -> dict:
    """Receive a status notification of the custom-domain service."""
    settings = get_settings()
    if not settings.custom_domain_webhook_secret:
        logger.error("Custom domain webhook refused: CUSTOM_DOMAIN_WEBHOOK_SECRET not set")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Custom domain webhooks are not configured",
        )

    body = await request.body()
    try:
        verify_signature(
            settings.custom_domain_webhook_secret,
            body,
            request.headers.get(SIGNATURE_HEADER),
            settings.custom_domain_webhook_tolerance,
        )
    except SignatureError as error:
        logger.warning("Custom domain webhook refused: %s", error)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    try:
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("not an object")
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload"
        ) from error

    delivery_id = str(event.get("id") or request.headers.get(DELIVERY_HEADER) or "")
    if not delivery_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing delivery id")

    # The service retries a delivery with the same id: process it once
    if await event_dedupe.already_processed(EVENT_NAMESPACE, delivery_id):
        return {"status": "duplicate"}

    async with async_session_factory() as db:
        try:
            outcome = await apply_event(db, event)
            await db.commit()
        except Exception as error:
            await db.rollback()
            logger.error("Failed to process custom domain webhook: %s", error)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process webhook",
            ) from error

    await event_dedupe.mark_processed(
        EVENT_NAMESPACE, delivery_id, settings.custom_domain_event_ttl
    )
    logger.info("Custom domain event %s %s: %s", event.get("event"), delivery_id, outcome)
    return {"status": outcome}
