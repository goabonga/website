# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/email-sender endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    EmailSenderResponse,
    UpdateEmailSenderRequest,
)
from auth.db.models.user import User
from auth.tasks.email import invalidate_platform_sender_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email-sender", tags=["me-organisations:email-sender"])


@router.get("/", response_model=EmailSenderResponse)
async def get_email_sender(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> EmailSenderResponse:
    """Get the email sender configuration for an organisation.

    Returns the outbound email address and display name stored in the
    organisation's settings. Both fields may be null if no custom sender has
    been configured yet.

    **Required scope:** org membership + `settings:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/email-sender/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:read",
    )

    settings = tenant.settings or {}
    return EmailSenderResponse(
        email_sender_address=settings.get("email_sender_address"),
        email_sender_name=settings.get("email_sender_name"),
    )


@router.patch("/", response_model=EmailSenderResponse)
async def update_email_sender(
    org_id: uuid.UUID,
    body: UpdateEmailSenderRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> EmailSenderResponse:
    """Update the email sender configuration for an organisation.

    Persists the outbound email address and display name in the organisation's
    settings, then invalidates the Celery worker sender cache so the new values
    take effect immediately for all queued emails.

    **Required scope:** org membership + `settings:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"email_sender_address": "no-reply@acme.com", "email_sender_name": "Acme"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/email-sender/
    ```
    """
    _user, tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="settings:write",
    )

    current = dict(tenant.settings) if tenant.settings else {}
    current["email_sender_address"] = body.email_sender_address
    current["email_sender_name"] = body.email_sender_name
    tenant.settings = current
    flag_modified(tenant, "settings")

    await db.flush()

    # Invalidate the Celery worker sender cache
    invalidate_platform_sender_cache()

    logger.info(
        "ACTION: me_email_sender_update, user_id=%s, org_id=%s",
        user.id,
        org_id,
    )

    return EmailSenderResponse(
        email_sender_address=current["email_sender_address"],
        email_sender_name=current["email_sender_name"],
    )
