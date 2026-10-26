# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Inbound email routes."""

import math
import uuid
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.config import settings
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.inbound import InboundAttachment, InboundEmail
from mailler.schemas.inbound import (
    AttachmentPayload,
    InboundEmailDetailResponse,
    InboundEmailListItem,
    InboundEmailListResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Inbound"])


@router.get("/inbound/attachments/{download_token}")
async def download_attachment(
    download_token: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download an inbound email attachment by its token.

    This endpoint is public (no auth required) as it uses
    unguessable tokens, matching Brevo's DownloadToken pattern.

    Args:
        download_token: UUID download token.
        db: Database session.

    Returns:
        File download response.

    Raises:
        HTTPException: If attachment not found or expired.
    """
    stmt = select(InboundAttachment).where(InboundAttachment.download_token == download_token)
    attachment = (await db.execute(stmt)).scalar_one_or_none()

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Check expiration
    from datetime import datetime

    if attachment.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Attachment expired")

    # Check file exists
    file_path = Path(attachment.file_path)
    if not file_path.exists():
        logger.error(
            "Attachment file missing",
            extra={"download_token": str(download_token), "file_path": str(file_path)},
        )
        raise HTTPException(status_code=404, detail="Attachment file not found")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


@router.get("/inbound/emails", response_model=InboundEmailListResponse)
async def list_inbound_emails(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    from_email: str | None = Query(default=None, description="Filter by sender"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> InboundEmailListResponse:
    """List inbound emails with pagination.

    The inbound mailbox is shared by the whole platform, so it is only
    readable with the administration scope.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.
        status: Optional status filter (received/forwarded/failed).
        from_email: Optional sender email filter.
        db: Database session.

    Returns:
        Paginated list of inbound emails.
    """
    # Build query
    stmt = select(InboundEmail).order_by(InboundEmail.created_at.desc())

    if status:
        stmt = stmt.where(InboundEmail.status == status)
    if from_email:
        stmt = stmt.where(InboundEmail.from_email.ilike(f"%{from_email}%"))

    # Get total count
    count_stmt = select(func.count(InboundEmail.id))
    if status:
        count_stmt = count_stmt.where(InboundEmail.status == status)
    if from_email:
        count_stmt = count_stmt.where(InboundEmail.from_email.ilike(f"%{from_email}%"))

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    emails = result.scalars().all()

    # Get attachment counts
    items = []
    for email_record in emails:
        att_count_stmt = select(func.count(InboundAttachment.id)).where(
            InboundAttachment.inbound_email_id == email_record.id
        )
        att_count = (await db.execute(att_count_stmt)).scalar() or 0

        items.append(
            InboundEmailListItem(
                id=str(email_record.id),
                from_email=email_record.from_email,
                from_name=email_record.from_name,
                subject=email_record.subject,
                status=email_record.status,
                received_at=email_record.received_at,
                forwarded_at=email_record.forwarded_at,
                created_at=email_record.created_at,
                attachment_count=att_count,
            )
        )

    return InboundEmailListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/inbound/emails/{email_id}", response_model=InboundEmailDetailResponse)
async def get_inbound_email(
    email_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> InboundEmailDetailResponse:
    """Get inbound email details by ID.

    Args:
        email_id: Inbound email UUID.
        db: Database session.

    Returns:
        Inbound email details with attachments.

    Raises:
        HTTPException: If email not found.
    """
    inbound = await db.get(InboundEmail, email_id)
    if not inbound:
        raise HTTPException(status_code=404, detail="Inbound email not found")

    # Load attachments
    att_stmt = select(InboundAttachment).where(InboundAttachment.inbound_email_id == email_id)
    attachments = (await db.execute(att_stmt)).scalars().all()

    attachment_payloads = [
        AttachmentPayload(
            Name=att.filename,
            ContentType=att.content_type,
            ContentLength=att.content_length,
            ContentID=att.content_id,
            DownloadToken=str(att.download_token),
        )
        for att in attachments
    ]

    return InboundEmailDetailResponse(
        id=str(inbound.id),
        message_id=inbound.message_id,
        in_reply_to=inbound.in_reply_to,
        from_email=inbound.from_email,
        from_name=inbound.from_name,
        to_emails=inbound.to_emails,
        cc_emails=inbound.cc_emails,
        reply_to_email=inbound.reply_to_email,
        reply_to_name=inbound.reply_to_name,
        subject=inbound.subject,
        html_body=inbound.html_body,
        text_body=inbound.text_body,
        headers=inbound.headers,
        sent_at_date=inbound.sent_at_date,
        spam_score=inbound.spam_score,
        status=inbound.status,
        webhook_response_code=inbound.webhook_response_code,
        error_message=inbound.error_message,
        retry_count=inbound.retry_count,
        received_at=inbound.received_at,
        forwarded_at=inbound.forwarded_at,
        created_at=inbound.created_at,
        attachments=attachment_payloads,
    )
