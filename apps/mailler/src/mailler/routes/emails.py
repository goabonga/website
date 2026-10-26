# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email retrieval routes."""

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.email import Email
from mailler.schemas.email import EmailDetailResponse, EmailListItem, EmailListResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Emails"])


@router.get("/emails", response_model=EmailListResponse)
async def list_emails(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    provider: str | None = Query(default=None, description="Filter by provider"),
    status: str | None = Query(default=None, description="Filter by status"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> EmailListResponse:
    """List the emails of the calling client with pagination.

    Administrators see the emails of every client.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        provider: Optional provider filter
        status: Optional status filter
        client_id: Optional client filter, honoured for administrators only
        db: Database session

    Returns:
        Paginated list of emails
    """
    # Build query
    stmt = auth.restrict(select(Email), Email.client_id, client_id).order_by(
        Email.created_at.desc()
    )

    if provider:
        stmt = stmt.where(Email.provider == provider)
    if status:
        stmt = stmt.where(Email.status == status)

    # Get total count
    count_stmt = auth.restrict(select(func.count(Email.id)), Email.client_id, client_id)
    if provider:
        count_stmt = count_stmt.where(Email.provider == provider)
    if status:
        count_stmt = count_stmt.where(Email.status == status)

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    emails = result.scalars().all()

    items = [
        EmailListItem(
            id=str(email.id),
            to_email=email.to_email,
            subject=email.subject,
            provider=email.provider,
            status=email.status,
            created_at=email.created_at,
            scheduled_at=email.scheduled_at,
            sent_at=email.sent_at,
        )
        for email in emails
    ]

    return EmailListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/emails/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> EmailDetailResponse:
    """Get email details by ID.

    An email of another client is reported as not found.

    Args:
        email_id: Email UUID
        db: Database session

    Returns:
        Email details

    Raises:
        HTTPException: If email not found
    """
    email = await db.get(Email, email_id)
    if not email or not auth.owns(email.client_id):
        logger.info("Email not found", extra={"email_id": str(email_id)})
        raise HTTPException(status_code=404, detail="Email not found")

    return EmailDetailResponse(
        id=str(email.id),
        to_email=email.to_email,
        to_name=email.to_name,
        from_email=email.from_email,
        from_name=email.from_name,
        reply_to=email.reply_to,
        subject=email.subject,
        html_content=email.html_content,
        text_content=email.text_content,
        provider=email.provider,
        provider_message_id=email.provider_message_id,
        status=email.status,
        error_message=email.error_message,
        retry_count=email.retry_count,
        scheduled_at=email.scheduled_at,
        queued_at=email.queued_at,
        sent_at=email.sent_at,
        delivered_at=email.delivered_at,
        bounced_at=email.bounced_at,
        failed_at=email.failed_at,
        created_at=email.created_at,
        metadata=email.metadata_,
        client_id=email.client_id,
        user_id=str(email.user_id) if email.user_id else None,
        task_id=email.task_id,
    )
