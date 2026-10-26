# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Webhook receiver for auth service events.

Validates the HMAC-SHA256 signature from auth and processes user
lifecycle events to keep the local user_cache in sync.

Subscribed events:
- user.created — insert new user cache entry
- user.updated — update email/name
- user.email_changed — update email
- user.deleted — remove from cache
"""

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.config import settings
from apt_server.database import get_db
from apt_server.db.models.user_cache import UserCache
from apt_server.logging import get_logger
from apt_server.services import user_cache

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"], include_in_schema=False)

# Signature tolerance: reject deliveries older than 5 minutes
SIGNATURE_MAX_AGE = 300


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """Verify the X-Webhook-Signature HMAC-SHA256 signature.

    Format: t=<unix_timestamp>,v1=<hex_digest>
    Signed message: "<timestamp>.<body>"
    """
    if not settings.webhook_secret:
        logger.warning("WEBHOOK_SECRET not configured, skipping signature check")
        return True

    parts = {}
    for pair in signature_header.split(","):
        key, _, value = pair.partition("=")
        parts[key.strip()] = value.strip()

    timestamp = parts.get("t", "")
    expected_sig = parts.get("v1", "")
    if not timestamp or not expected_sig:
        return False

    # Reject old signatures
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > SIGNATURE_MAX_AGE:
            logger.warning("webhook signature too old: %s", timestamp)
            return False
    except ValueError:
        return False

    # Compute expected HMAC
    message = f"{timestamp}.".encode() + body
    digest = hmac.new(settings.webhook_secret.encode(), message, hashlib.sha256).hexdigest()

    return hmac.compare_digest(digest, expected_sig)


@router.post("/auth")
async def receive_auth_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_signature: Annotated[str, Header()],
    x_webhook_event: Annotated[str, Header()],
) -> dict:
    """Receive and process auth service webhook events."""
    body = await request.body()

    if not _verify_signature(body, x_webhook_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    payload = await request.json()
    event = payload.get("event", x_webhook_event)
    data = payload.get("data", {})

    logger.info("webhook received: event=%s", event)

    if event in ("user.created", "user.updated", "user.email_changed", "user.email_verified"):
        sub = data.get("user_id") or data.get("id") or ""
        email = data.get("email") or data.get("new_email") or ""
        name = data.get("name") or data.get("display_name") or ""
        avatar_url = data.get("picture") or data.get("avatar_url") or ""

        if sub and email:
            await user_cache.upsert(db, sub=str(sub), email=email, name=name, avatar_url=avatar_url)
            logger.info("user_cache updated: sub=%s email=%s", sub, email)

            # If email changed, update ACL entries referencing the old email
            old_email = data.get("old_email") or data.get("previous_email")
            if old_email and old_email != email:
                from sqlalchemy import update

                from apt_server.db.models import PackageACL

                result = await db.execute(
                    update(PackageACL)
                    .where(PackageACL.grantee_user_id == old_email)
                    .values(grantee_user_id=email)
                )
                if result.rowcount:
                    logger.info(
                        "updated %d ACL entries: %s -> %s", result.rowcount, old_email, email
                    )
                await db.commit()

    elif event == "user.deleted":
        sub = str(data.get("user_id") or data.get("id") or "")
        if sub:
            await db.execute(delete(UserCache).where(UserCache.sub == sub))
            await db.commit()
            logger.info("user_cache deleted: sub=%s", sub)

    return {"status": "ok"}
