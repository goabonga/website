# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email scheduling route."""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus
from mailler.schemas.email import ScheduleEmailRequest, SendEmailResponse
from mailler.services import clients, idempotency
from mailler.services.template_content import resolve_content

logger = get_logger(__name__)

router = APIRouter(tags=["Schedule"])


@router.post("/schedule", response_model=SendEmailResponse)
async def schedule_email(
    request: ScheduleEmailRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias=idempotency.HEADER,
        min_length=1,
        max_length=idempotency.MAX_LENGTH,
        description="Makes the request safe to repeat: the first email is returned again",
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> SendEmailResponse:
    """Schedule an email for future delivery.

    The email will be processed by Celery Beat at the scheduled time.
    Repeating a request with the same ``Idempotency-Key`` returns the first
    email instead of scheduling a second one.

    Args:
        request: Email details with scheduled time
        idempotency_key: Optional key that makes the request safe to repeat
        db: Database session

    Returns:
        SendEmailResponse with email ID
    """
    existing = await idempotency.find_replay(db, auth.client_id, idempotency_key, request.to_email)
    if existing is not None:
        return idempotency.replay_response(existing)

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
    content = await resolve_content(db, auth, request)

    # Create email record with scheduled time
    # For machine clients (client_credentials), user_id should be None
    # Only real users have a UUID as user_id
    email = Email(
        to_email=request.to_email,
        to_name=request.to_name,
        from_email=identity.from_email,
        from_name=identity.from_name,
        reply_to=identity.reply_to,
        subject=content.subject,
        html_content=content.html,
        text_content=content.text,
        provider=identity.provider,
        metadata_=content.metadata,
        client_id=auth.user.client_id,
        user_id=None if auth.user.is_machine_client else auth.user.id,
        status=EmailStatus.PENDING.value,
        scheduled_at=request.scheduled_at,
        idempotency_key=idempotency_key,
    )

    try:
        db.add(email)
        await db.commit()
    except IntegrityError:
        # A concurrent request with the same key won the race
        await db.rollback()
        existing = await idempotency.find_replay(
            db, auth.client_id, idempotency_key, request.to_email
        )
        if existing is None:
            raise
        return idempotency.replay_response(existing)
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
        missing_variables=content.missing_variables,
    )
