# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email campaign CRUD and action routes."""

import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.campaign import CampaignStatus, EmailCampaign, EmailSend
from mailler.models.contact import Contact, ContactGroup, ContactGroupMember
from mailler.models.template import EmailTemplate
from mailler.schemas.campaign import (
    CampaignCreate,
    CampaignGroupEmbed,
    CampaignListItem,
    CampaignListResponse,
    CampaignPreview,
    CampaignResponse,
    CampaignStats,
    CampaignTemplateEmbed,
    CampaignUpdate,
    EmailSendListItem,
    EmailSendListResponse,
    PauseCampaignResponse,
    ScheduleCampaignRequest,
    ScheduleCampaignResponse,
    SendCampaignResponse,
)
from mailler.tasks.send import send_campaign_task

logger = get_logger(__name__)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def build_campaign_stats(campaign: EmailCampaign) -> CampaignStats:
    """Build stats object from campaign."""
    return CampaignStats(
        total_recipients=campaign.total_recipients,
        sent_count=campaign.sent_count,
        delivered_count=campaign.delivered_count,
        opened_count=campaign.opened_count,
        clicked_count=campaign.clicked_count,
        bounced_count=campaign.bounced_count,
        complained_count=campaign.complained_count,
        failed_count=campaign.failed_count,
        progress_percent=campaign.progress_percent,
        open_rate=campaign.open_rate,
        click_rate=campaign.click_rate,
        bounce_rate=campaign.bounce_rate,
        complaint_rate=campaign.complaint_rate,
    )


async def get_campaign_with_relations(db: AsyncSession, campaign_id: int) -> EmailCampaign | None:
    """Load campaign with all nested relationships for response building."""
    stmt = (
        select(EmailCampaign)
        .where(EmailCampaign.id == campaign_id)
        .options(
            selectinload(EmailCampaign.template),
            selectinload(EmailCampaign.group).selectinload(ContactGroup.members),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def build_campaign_response(campaign: EmailCampaign) -> CampaignResponse:
    """Build full campaign response with embedded template and group."""
    template_embed = None
    if campaign.template:
        template_embed = CampaignTemplateEmbed(
            id=campaign.template.id,
            name=campaign.template.name,
            subject=campaign.template.subject_template,
        )

    group_embed = None
    if campaign.group:
        group_embed = CampaignGroupEmbed(
            id=campaign.group.id,
            name=campaign.group.name,
            member_count=campaign.group.member_count,
        )

    return CampaignResponse(
        id=campaign.id,
        client_id=campaign.client_id,
        name=campaign.name,
        description=campaign.description,
        template_id=campaign.template_id,
        group_id=campaign.group_id,
        template=template_embed,
        group=group_embed,
        status=campaign.status,
        scheduled_at=campaign.scheduled_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        from_name=campaign.from_name,
        from_email=campaign.from_email,
        reply_to=campaign.reply_to,
        provider=campaign.provider,
        subject_override=campaign.subject_override,
        task_id=campaign.task_id,
        metadata=campaign.metadata_,
        stats=build_campaign_stats(campaign),
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Search in name"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> CampaignListResponse:
    """List the campaigns of the calling client with pagination.

    Administrators see the campaigns of every client.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        status: Optional status filter
        search: Optional search term
        client_id: Optional client filter, honoured for administrators only
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of campaigns
    """
    # Build query
    stmt = auth.restrict(select(EmailCampaign), EmailCampaign.client_id, client_id).order_by(
        EmailCampaign.created_at.desc()
    )

    if status:
        stmt = stmt.where(EmailCampaign.status == status)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(EmailCampaign.name.ilike(search_pattern))

    # Get total count
    count_stmt = auth.restrict(
        select(func.count(EmailCampaign.id)), EmailCampaign.client_id, client_id
    )
    if status:
        count_stmt = count_stmt.where(EmailCampaign.status == status)
    if search:
        count_stmt = count_stmt.where(EmailCampaign.name.ilike(search_pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page with relationships loaded
    offset = (page - 1) * page_size
    stmt = (
        stmt.offset(offset)
        .limit(page_size)
        .options(
            selectinload(EmailCampaign.template),
            selectinload(EmailCampaign.group).selectinload(ContactGroup.members),
        )
    )
    result = await db.execute(stmt)
    campaigns = result.scalars().all()

    items = []
    for c in campaigns:
        template_embed = None
        if c.template:
            template_embed = CampaignTemplateEmbed(
                id=c.template.id,
                name=c.template.name,
                subject=c.template.subject_template,
            )

        group_embed = None
        if c.group:
            group_embed = CampaignGroupEmbed(
                id=c.group.id,
                name=c.group.name,
                member_count=c.group.member_count,
            )

        items.append(
            CampaignListItem(
                id=c.id,
                name=c.name,
                description=c.description,
                status=c.status,
                template_id=c.template_id,
                group_id=c.group_id,
                template=template_embed,
                group=group_embed,
                total_recipients=c.total_recipients,
                sent_count=c.sent_count,
                progress_percent=c.progress_percent,
                scheduled_at=c.scheduled_at,
                started_at=c.started_at,
                completed_at=c.completed_at,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )

    return CampaignListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    request: CampaignCreate,
    client_id: str | None = Query(
        default=None, description="Administrators only: client the campaign is created for"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> CampaignResponse:
    """Create a new campaign.

    Args:
        request: Campaign data
        db: Database session
        auth: Authentication context

    Returns:
        Created campaign

    Raises:
        HTTPException: If template or group not found
    """
    owner = auth.target_client_id(client_id)

    # Validate template exists (for the same client) if provided
    if request.template_id:
        template = await db.get(EmailTemplate, request.template_id)
        if not template or template.client_id != owner:
            raise HTTPException(status_code=404, detail="Template not found")

    # Validate group exists (for the same client) if provided
    if request.group_id:
        group = await db.get(ContactGroup, request.group_id)
        if not group or group.client_id != owner:
            raise HTTPException(status_code=404, detail="Contact group not found")

    # Determine initial status
    initial_status = CampaignStatus.DRAFT.value
    if request.scheduled_at:
        initial_status = CampaignStatus.SCHEDULED.value

    campaign = EmailCampaign(
        client_id=owner,
        name=request.name,
        description=request.description,
        template_id=request.template_id,
        group_id=request.group_id,
        status=initial_status,
        scheduled_at=request.scheduled_at,
        from_name=request.from_name,
        from_email=request.from_email,
        reply_to=request.reply_to,
        provider=request.provider,
        subject_override=request.subject_override,
        metadata_=request.metadata or {},
    )

    db.add(campaign)
    await db.commit()

    # Save ID before expiring (accessing expired object triggers sync load)
    campaign_id = campaign.id

    # Expire cached objects to ensure fresh load with all relationships
    db.expire_all()

    # Reload campaign with all nested relationships
    reloaded = await get_campaign_with_relations(db, campaign_id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="Campaign not found after creation")

    logger.info(
        "Campaign created",
        extra={
            "campaign_id": reloaded.id,
            "campaign_name": reloaded.name,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return build_campaign_response(reloaded)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> CampaignResponse:
    """Get campaign by ID.

    A campaign of another client is reported as not found.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Returns:
        Campaign details

    Raises:
        HTTPException: If campaign not found
    """
    campaign = await get_campaign_with_relations(db, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    return build_campaign_response(campaign)


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    request: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> CampaignResponse:
    """Update a campaign.

    Only draft or scheduled campaigns can be updated.

    Args:
        campaign_id: Campaign ID
        request: Updated campaign data
        db: Database session
        auth: Authentication context

    Returns:
        Updated campaign

    Raises:
        HTTPException: If campaign not found or cannot be edited
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Only allow editing draft or scheduled campaigns
    if campaign.status not in [
        CampaignStatus.DRAFT.value,
        CampaignStatus.SCHEDULED.value,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit campaign with status '{campaign.status}'",
        )

    # Validate template if being changed
    if request.template_id is not None:
        template = await db.get(EmailTemplate, request.template_id)
        if not template or template.client_id != campaign.client_id:
            raise HTTPException(status_code=404, detail="Template not found")
        campaign.template_id = request.template_id

    # Validate group if being changed
    if request.group_id is not None:
        group = await db.get(ContactGroup, request.group_id)
        if not group or group.client_id != campaign.client_id:
            raise HTTPException(status_code=404, detail="Contact group not found")
        campaign.group_id = request.group_id

    # Update other fields
    if request.name is not None:
        campaign.name = request.name
    if request.description is not None:
        campaign.description = request.description
    if request.from_name is not None:
        campaign.from_name = request.from_name
    if request.from_email is not None:
        campaign.from_email = request.from_email
    if request.reply_to is not None:
        campaign.reply_to = request.reply_to
    if request.provider is not None:
        campaign.provider = request.provider
    if request.subject_override is not None:
        campaign.subject_override = request.subject_override
    if request.scheduled_at is not None:
        campaign.scheduled_at = request.scheduled_at
        if campaign.status == CampaignStatus.DRAFT.value:
            campaign.status = CampaignStatus.SCHEDULED.value
    if request.metadata is not None:
        campaign.metadata_ = request.metadata

    await db.commit()

    # Save ID before expiring (accessing expired object triggers sync load)
    campaign_id = campaign.id

    # Expire cached objects to ensure fresh load with all relationships
    db.expire_all()

    # Reload campaign with all nested relationships
    reloaded = await get_campaign_with_relations(db, campaign_id)
    if reloaded is None:
        raise HTTPException(status_code=404, detail="Campaign not found after update")

    logger.info(
        "Campaign updated",
        extra={
            "campaign_id": reloaded.id,
            "campaign_name": reloaded.name,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return build_campaign_response(reloaded)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:write")),
) -> None:
    """Delete a campaign.

    Campaigns can be deleted in any status except 'sending'.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Raises:
        HTTPException: If campaign not found or currently sending
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Cannot delete campaigns that are currently sending
    if campaign.status == CampaignStatus.SENDING.value:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete campaign while sending",
        )

    logger.info(
        "Campaign deleted",
        extra={
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    await db.delete(campaign)
    await db.commit()


@router.post("/{campaign_id}/schedule", response_model=ScheduleCampaignResponse)
async def schedule_campaign(
    campaign_id: int,
    request: ScheduleCampaignRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> ScheduleCampaignResponse:
    """Schedule a campaign for future sending.

    Args:
        campaign_id: Campaign ID
        request: Schedule details
        db: Database session
        auth: Authentication context

    Returns:
        Schedule confirmation

    Raises:
        HTTPException: If campaign not found or cannot be scheduled
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate can be scheduled
    if campaign.status not in [
        CampaignStatus.DRAFT.value,
        CampaignStatus.SCHEDULED.value,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot schedule campaign with status '{campaign.status}'",
        )

    # Validate template and group are set
    if not campaign.template_id:
        raise HTTPException(status_code=400, detail="Campaign must have a template")
    if not campaign.group_id:
        raise HTTPException(status_code=400, detail="Campaign must have a contact group")

    campaign.scheduled_at = request.scheduled_at
    campaign.status = CampaignStatus.SCHEDULED.value

    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign scheduled",
        extra={
            "campaign_id": campaign.id,
            "scheduled_at": str(request.scheduled_at),
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return ScheduleCampaignResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        scheduled_at=campaign.scheduled_at,
        message="Campaign scheduled successfully",
    )


@router.post("/{campaign_id}/send", response_model=SendCampaignResponse)
async def start_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> SendCampaignResponse:
    """Start sending a campaign immediately.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Returns:
        Send confirmation

    Raises:
        HTTPException: If campaign not found or cannot be started
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Validate can be started
    if campaign.status not in [
        CampaignStatus.DRAFT.value,
        CampaignStatus.SCHEDULED.value,
    ]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start campaign with status '{campaign.status}'",
        )

    # Validate template and group are set
    if not campaign.template_id:
        raise HTTPException(status_code=400, detail="Campaign must have a template")
    if not campaign.group_id:
        raise HTTPException(status_code=400, detail="Campaign must have a contact group")

    # Count recipients
    count_stmt = (
        select(func.count(Contact.id))
        .join(ContactGroupMember)
        .where(ContactGroupMember.group_id == campaign.group_id)
        .where(Contact.client_id == campaign.client_id)
        .where(Contact.status == "active")
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    if total == 0:
        raise HTTPException(
            status_code=400,
            detail="No active contacts in the selected group",
        )

    # Update campaign
    campaign.status = CampaignStatus.SENDING.value
    campaign.started_at = datetime.now(UTC)
    campaign.total_recipients = total

    await db.commit()

    # Queue Celery task to process sends
    task = send_campaign_task.delay(campaign.id)
    campaign.task_id = task.id
    await db.commit()

    logger.info(
        "Campaign started",
        extra={
            "campaign_id": campaign.id,
            "total_recipients": total,
            "task_id": task.id,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return SendCampaignResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        task_id=campaign.task_id,
        total_recipients=total,
        message="Campaign sending started",
    )


@router.post("/{campaign_id}/pause", response_model=PauseCampaignResponse)
async def pause_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> PauseCampaignResponse:
    """Pause a sending campaign.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Returns:
        Pause confirmation

    Raises:
        HTTPException: If campaign not found or cannot be paused
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatus.SENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause campaign with status '{campaign.status}'",
        )

    campaign.status = CampaignStatus.PAUSED.value

    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign paused",
        extra={
            "campaign_id": campaign.id,
            "sent_count": campaign.sent_count,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return PauseCampaignResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        sent_count=campaign.sent_count,
        message="Campaign paused",
    )


@router.post("/{campaign_id}/resume", response_model=SendCampaignResponse)
async def resume_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:send")),
) -> SendCampaignResponse:
    """Resume a paused campaign.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Returns:
        Resume confirmation

    Raises:
        HTTPException: If campaign not found or cannot be resumed
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatus.PAUSED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume campaign with status '{campaign.status}'",
        )

    campaign.status = CampaignStatus.SENDING.value

    await db.commit()

    # Queue Celery task to continue processing sends
    task = send_campaign_task.delay(campaign.id)
    campaign.task_id = task.id
    await db.commit()

    logger.info(
        "Campaign resumed",
        extra={
            "campaign_id": campaign.id,
            "sent_count": campaign.sent_count,
            "task_id": task.id,
            "user_id": str(auth.user.id) if auth.user.id else None,
        },
    )

    return SendCampaignResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        task_id=campaign.task_id,
        total_recipients=campaign.total_recipients,
        message="Campaign resumed",
    )


@router.get("/{campaign_id}/preview", response_model=CampaignPreview)
async def preview_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> CampaignPreview:
    """Preview a campaign with sample data.

    Args:
        campaign_id: Campaign ID
        db: Database session
        auth: Authentication context

    Returns:
        Rendered preview

    Raises:
        HTTPException: If campaign not found
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.template_id:
        raise HTTPException(status_code=400, detail="Campaign must have a template")

    template = await db.get(EmailTemplate, campaign.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Count recipients
    recipient_count = 0
    if campaign.group_id:
        count_stmt = (
            select(func.count(Contact.id))
            .join(ContactGroupMember)
            .where(ContactGroupMember.group_id == campaign.group_id)
            .where(Contact.client_id == campaign.client_id)
            .where(Contact.status == "active")
        )
        recipient_count = (await db.execute(count_stmt)).scalar() or 0

    # Use subject override or template subject
    subject = campaign.subject_override or template.subject_template

    return CampaignPreview(
        subject=subject,
        html=template.html_compiled or "",
        plain_text=template.plain_text,
        recipient_count=recipient_count,
    )


@router.get("/{campaign_id}/sends", response_model=EmailSendListResponse)
async def list_campaign_sends(
    campaign_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> EmailSendListResponse:
    """List sends for a campaign.

    Args:
        campaign_id: Campaign ID
        page: Page number
        page_size: Items per page
        status: Optional status filter
        db: Database session
        auth: Authentication context

    Returns:
        Paginated list of sends

    Raises:
        HTTPException: If campaign not found
    """
    campaign = await db.get(EmailCampaign, campaign_id)
    if not campaign or not auth.owns(campaign.client_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Build query
    stmt = (
        select(EmailSend)
        .where(EmailSend.campaign_id == campaign_id)
        .order_by(EmailSend.created_at.desc())
    )

    if status:
        stmt = stmt.where(EmailSend.status == status)

    # Get total count
    count_stmt = select(func.count(EmailSend.id)).where(EmailSend.campaign_id == campaign_id)
    if status:
        count_stmt = count_stmt.where(EmailSend.status == status)

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    # Get page
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    sends = result.scalars().all()

    items = [
        EmailSendListItem(
            id=s.id,
            recipient_email=s.recipient_email,
            recipient_name=s.recipient_name,
            status=s.status,
            sent_at=s.sent_at,
            delivered_at=s.delivered_at,
            opened_at=s.opened_at,
            error_message=s.error_message,
        )
        for s in sends
    ]

    return EmailSendListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
