# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email sending route."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.config import settings
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus
from mailler.schemas.email import SendEmailRequest, SendEmailResponse
from mailler.tasks.send import send_email_task

logger = get_logger(__name__)

router = APIRouter(tags=["Send"])


@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    request: SendEmailRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> SendEmailResponse:
    """Send an email immediately (async via Celery).

    The email is queued for immediate delivery via the specified provider.

    Args:
        request: Email details
        db: Database session

    Returns:
        SendEmailResponse with email ID and task ID
    """
    from_email = request.from_email or settings.default_from
    if not from_email:
        raise HTTPException(
            status_code=422,
            detail="No sender address: provide from_email or configure DEFAULT_FROM",
        )

    # Create email record
    # For machine clients (client_credentials), user_id should be None
    # Only real users have a UUID as user_id
    email = Email(
        to_email=request.to_email,
        to_name=request.to_name,
        from_email=from_email,
        from_name=request.from_name or settings.default_from_name,
        reply_to=request.reply_to,
        subject=request.subject,
        html_content=request.html_content,
        text_content=request.text_content,
        provider=request.provider,
        metadata_=request.metadata or {},
        client_id=auth.user.client_id,
        user_id=None if auth.user.is_machine_client else auth.user.id,
        status=EmailStatus.PENDING.value,
    )

    db.add(email)
    await db.commit()
    await db.refresh(email)

    # Queue Celery task for immediate sending
    task = send_email_task.delay(str(email.id))

    logger.info(
        "Email queued for sending",
        extra={
            "email_id": str(email.id),
            "task_id": task.id,
            "provider": request.provider,
            "to": request.to_email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return SendEmailResponse(
        id=str(email.id),
        status="queued",
        message="Email queued for delivery",
        task_id=task.id,
    )
