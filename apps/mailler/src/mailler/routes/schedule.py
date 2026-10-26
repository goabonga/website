# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email scheduling route."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus
from mailler.schemas.email import ScheduleEmailRequest, SendEmailResponse
from mailler.services import clients

logger = get_logger(__name__)

router = APIRouter(tags=["Schedule"])


@router.post("/schedule", response_model=SendEmailResponse)
async def schedule_email(
    request: ScheduleEmailRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> SendEmailResponse:
    """Schedule an email for future delivery.

    The email will be processed by Celery Beat at the scheduled time.

    Args:
        request: Email details with scheduled time
        db: Database session

    Returns:
        SendEmailResponse with email ID
    """
    # The sender and the provider come from the record of the client
    client = await clients.get_client(db, auth.client_id)
    identity = clients.resolve_identity(
        client,
        is_admin=auth.is_admin,
        from_email=request.from_email,
        from_name=request.from_name,
        reply_to=request.reply_to,
        provider=request.provider,
    )
    await clients.enforce_limits(db, client, is_admin=auth.is_admin)

    # Create email record with scheduled time
    # For machine clients (client_credentials), user_id should be None
    # Only real users have a UUID as user_id
    email = Email(
        to_email=request.to_email,
        to_name=request.to_name,
        from_email=identity.from_email,
        from_name=identity.from_name,
        reply_to=identity.reply_to,
        subject=request.subject,
        html_content=request.html_content,
        text_content=request.text_content,
        provider=identity.provider,
        metadata_=request.metadata or {},
        client_id=auth.user.client_id,
        user_id=None if auth.user.is_machine_client else auth.user.id,
        status=EmailStatus.PENDING.value,
        scheduled_at=request.scheduled_at,
    )

    db.add(email)
    await db.commit()
    await db.refresh(email)

    logger.info(
        "Email scheduled",
        extra={
            "email_id": str(email.id),
            "scheduled_at": request.scheduled_at.isoformat(),
            "provider": identity.provider,
            "to": request.to_email,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return SendEmailResponse(
        id=str(email.id),
        status="scheduled",
        message=f"Email scheduled for {request.scheduled_at.isoformat()}",
        task_id=None,
    )
