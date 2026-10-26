# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Secured analytics stats API routes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.auth.dependencies import require_scopes
from analytics.auth.models import User
from analytics.database import get_db
from analytics.models.campaign import Campaign, CampaignClick, Pixel
from analytics.models.event import Event
from analytics.models.session import Session

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


# Response models
class OverviewStats(BaseModel):
    """Overview statistics."""

    total_sessions: int
    unique_visitors: int
    total_pageviews: int
    total_events: int
    period_start: datetime
    period_end: datetime


class DailyStats(BaseModel):
    """Daily statistics."""

    date: str
    sessions: int
    pageviews: int
    unique_visitors: int


class CountryStats(BaseModel):
    """Statistics by country."""

    country: str | None
    sessions: int
    percentage: float


class DeviceStats(BaseModel):
    """Statistics by device type."""

    device_type: str | None
    sessions: int
    percentage: float


class BrowserStats(BaseModel):
    """Statistics by browser."""

    browser: str | None
    sessions: int
    percentage: float


class ReferrerStats(BaseModel):
    """Statistics by referrer."""

    referrer: str | None
    sessions: int
    percentage: float


class IPStats(BaseModel):
    """Statistics by IP address."""

    ip_address: str
    sessions: int
    pageviews: int
    countries: list[str]
    browsers: list[str]
    device_types: list[str]
    first_seen: datetime
    last_seen: datetime


class IPPageStats(BaseModel):
    """Page statistics for an IP address."""

    page_url: str | None
    pageviews: int


class IPEventStats(BaseModel):
    """Event statistics for an IP address."""

    event_type: str
    count: int


class IPDetailStats(BaseModel):
    """Detailed statistics for a specific IP address."""

    ip_address: str
    total_sessions: int
    total_pageviews: int
    total_events: int
    countries: list[str]
    cities: list[str]
    browsers: list[str]
    device_types: list[str]
    operating_systems: list[str]
    referrers: list[str]
    first_seen: datetime
    last_seen: datetime
    sessions_by_day: list[DailyStats]
    pages: list[IPPageStats] = []
    events: list[IPEventStats] = []


class PageStats(BaseModel):
    """Statistics by page."""

    page_url: str | None
    pageviews: int
    unique_sessions: int


class EventStats(BaseModel):
    """Statistics by event type."""

    event_type: str
    count: int
    unique_sessions: int


class CampaignStats(BaseModel):
    """Campaign statistics."""

    id: UUID
    name: str
    tracking_key: str
    is_active: bool
    click_count: int
    unique_click_count: int
    pixel_count: int
    total_opens: int
    created_at: datetime


class CampaignDetail(BaseModel):
    """Detailed campaign statistics."""

    id: UUID
    name: str
    description: str | None
    tracking_key: str
    destination_url: str | None
    is_active: bool
    click_count: int
    unique_click_count: int
    created_at: datetime
    updated_at: datetime
    clicks_by_day: list[DailyStats]
    clicks_by_country: list[CountryStats]


class PixelStats(BaseModel):
    """Pixel statistics."""

    id: UUID
    pixel_key: str
    recipient_email: str | None
    recipient_id: str | None
    open_count: int
    first_opened_at: datetime | None
    last_opened_at: datetime | None
    created_at: datetime


class StatsResponse(BaseModel):
    """Generic stats response wrapper."""

    success: bool = True
    data: dict | list


def get_date_range(days: int) -> tuple[datetime, datetime]:
    """Get date range for the given number of days."""
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    return start, end


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> OverviewStats:
    """Get overview statistics for the analytics dashboard."""
    start, end = get_date_range(days)

    # Total sessions
    sessions_result = await db.execute(
        select(func.count(Session.id)).where(Session.first_seen >= start)
    )
    total_sessions = sessions_result.scalar() or 0

    # Unique visitors (by IP)
    unique_result = await db.execute(
        select(func.count(func.distinct(Session.ip_address))).where(Session.first_seen >= start)
    )
    unique_visitors = unique_result.scalar() or 0

    # Total pageviews
    pageviews_result = await db.execute(
        select(func.count(Event.id))
        .join(Session, Event.session_id == Session.id)
        .where(Session.first_seen >= start, Event.event_type == "pageview")
    )
    total_pageviews = pageviews_result.scalar() or 0

    # Total events
    events_result = await db.execute(
        select(func.count(Event.id))
        .join(Session, Event.session_id == Session.id)
        .where(Session.first_seen >= start)
    )
    total_events = events_result.scalar() or 0

    return OverviewStats(
        total_sessions=total_sessions,
        unique_visitors=unique_visitors,
        total_pageviews=total_pageviews,
        total_events=total_events,
        period_start=start,
        period_end=end,
    )


@router.get("/daily", response_model=list[DailyStats])
async def get_daily_stats(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[DailyStats]:
    """Get daily statistics for the analytics dashboard."""
    start, end = get_date_range(days)

    # Daily sessions and unique visitors
    daily_result = await db.execute(
        select(
            func.date(Session.first_seen).label("date"),
            func.count(Session.id).label("sessions"),
            func.count(func.distinct(Session.ip_address)).label("unique_visitors"),
        )
        .where(Session.first_seen >= start)
        .group_by(func.date(Session.first_seen))
        .order_by(func.date(Session.first_seen))
    )
    daily_data = daily_result.all()

    # Daily pageviews
    pageviews_result = await db.execute(
        select(
            func.date(Event.timestamp).label("date"),
            func.count(Event.id).label("pageviews"),
        )
        .join(Session, Event.session_id == Session.id)
        .where(Session.first_seen >= start, Event.event_type == "pageview")
        .group_by(func.date(Event.timestamp))
    )
    pageviews_by_date = {str(row.date): row.pageviews for row in pageviews_result.all()}

    return [
        DailyStats(
            date=str(row.date),
            sessions=row.sessions,
            pageviews=pageviews_by_date.get(str(row.date), 0),
            unique_visitors=row.unique_visitors,
        )
        for row in daily_data
    ]


@router.get("/countries", response_model=list[CountryStats])
async def get_country_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[CountryStats]:
    """Get statistics by country."""
    start, _ = get_date_range(days)

    # Total sessions for percentage calculation
    total_result = await db.execute(
        select(func.count(Session.id)).where(Session.first_seen >= start)
    )
    total_sessions = total_result.scalar() or 1

    # Sessions by country
    result = await db.execute(
        select(
            Session.country,
            func.count(Session.id).label("sessions"),
        )
        .where(Session.first_seen >= start)
        .group_by(Session.country)
        .order_by(func.count(Session.id).desc())
        .limit(limit)
    )

    return [
        CountryStats(
            country=row.country,
            sessions=row.sessions,
            percentage=round(row.sessions / total_sessions * 100, 2),
        )
        for row in result.all()
    ]


@router.get("/devices", response_model=list[DeviceStats])
async def get_device_stats(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[DeviceStats]:
    """Get statistics by device type."""
    start, _ = get_date_range(days)

    # Total sessions for percentage calculation
    total_result = await db.execute(
        select(func.count(Session.id)).where(Session.first_seen >= start)
    )
    total_sessions = total_result.scalar() or 1

    # Sessions by device type
    result = await db.execute(
        select(
            Session.device_type,
            func.count(Session.id).label("sessions"),
        )
        .where(Session.first_seen >= start)
        .group_by(Session.device_type)
        .order_by(func.count(Session.id).desc())
    )

    return [
        DeviceStats(
            device_type=row.device_type,
            sessions=row.sessions,
            percentage=round(row.sessions / total_sessions * 100, 2),
        )
        for row in result.all()
    ]


@router.get("/browsers", response_model=list[BrowserStats])
async def get_browser_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[BrowserStats]:
    """Get statistics by browser."""
    start, _ = get_date_range(days)

    # Total sessions for percentage calculation
    total_result = await db.execute(
        select(func.count(Session.id)).where(Session.first_seen >= start)
    )
    total_sessions = total_result.scalar() or 1

    # Sessions by browser
    result = await db.execute(
        select(
            Session.browser,
            func.count(Session.id).label("sessions"),
        )
        .where(Session.first_seen >= start)
        .group_by(Session.browser)
        .order_by(func.count(Session.id).desc())
        .limit(limit)
    )

    return [
        BrowserStats(
            browser=row.browser,
            sessions=row.sessions,
            percentage=round(row.sessions / total_sessions * 100, 2),
        )
        for row in result.all()
    ]


@router.get("/ips", response_model=list[IPStats])
async def get_ip_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[IPStats]:
    """Get statistics by IP address (most active IPs)."""
    start, _ = get_date_range(days)

    # Get top IPs by session count
    result = await db.execute(
        select(
            Session.ip_address,
            func.count(Session.id).label("sessions"),
            func.min(Session.first_seen).label("first_seen"),
            func.max(Session.last_seen).label("last_seen"),
            func.array_agg(func.distinct(Session.country)).label("countries"),
            func.array_agg(func.distinct(Session.browser)).label("browsers"),
            func.array_agg(func.distinct(Session.device_type)).label("device_types"),
        )
        .where(Session.first_seen >= start, Session.ip_address.isnot(None))
        .group_by(Session.ip_address)
        .order_by(func.count(Session.id).desc())
        .limit(limit)
    )
    ip_data = result.all()

    # Get pageviews for each IP
    ip_stats = []
    for row in ip_data:
        pageviews_result = await db.execute(
            select(func.count(Event.id))
            .join(Session, Event.session_id == Session.id)
            .where(
                Session.ip_address == row.ip_address,
                Session.first_seen >= start,
                Event.event_type == "pageview",
            )
        )
        pageviews = pageviews_result.scalar() or 0

        ip_stats.append(
            IPStats(
                ip_address=str(row.ip_address),
                sessions=row.sessions,
                pageviews=pageviews,
                countries=[c for c in (row.countries or []) if c],
                browsers=[b for b in (row.browsers or []) if b],
                device_types=[d for d in (row.device_types or []) if d],
                first_seen=row.first_seen,
                last_seen=row.last_seen,
            )
        )

    return ip_stats


@router.get("/ips/{ip_address:path}", response_model=IPDetailStats)
async def get_ip_detail(
    ip_address: str,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> IPDetailStats:
    """Get detailed statistics for a specific IP address."""
    from fastapi import HTTPException

    start, _ = get_date_range(days)

    # Check if IP has any sessions
    check_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.ip_address == ip_address, Session.first_seen >= start
        )
    )
    if not check_result.scalar():
        raise HTTPException(status_code=404, detail="IP address not found")

    # Aggregated stats
    agg_result = await db.execute(
        select(
            func.count(Session.id).label("sessions"),
            func.min(Session.first_seen).label("first_seen"),
            func.max(Session.last_seen).label("last_seen"),
            func.array_agg(func.distinct(Session.country)).label("countries"),
            func.array_agg(func.distinct(Session.city)).label("cities"),
            func.array_agg(func.distinct(Session.browser)).label("browsers"),
            func.array_agg(func.distinct(Session.device_type)).label("device_types"),
            func.array_agg(func.distinct(Session.os)).label("operating_systems"),
            func.array_agg(func.distinct(Session.referrer)).label("referrers"),
        ).where(Session.ip_address == ip_address, Session.first_seen >= start)
    )
    agg_data = agg_result.one()

    # Total pageviews
    pageviews_result = await db.execute(
        select(func.count(Event.id))
        .join(Session, Event.session_id == Session.id)
        .where(
            Session.ip_address == ip_address,
            Session.first_seen >= start,
            Event.event_type == "pageview",
        )
    )
    total_pageviews = pageviews_result.scalar() or 0

    # Total events
    events_result = await db.execute(
        select(func.count(Event.id))
        .join(Session, Event.session_id == Session.id)
        .where(Session.ip_address == ip_address, Session.first_seen >= start)
    )
    total_events = events_result.scalar() or 0

    # Sessions by day
    daily_result = await db.execute(
        select(
            func.date(Session.first_seen).label("date"),
            func.count(Session.id).label("sessions"),
        )
        .where(Session.ip_address == ip_address, Session.first_seen >= start)
        .group_by(func.date(Session.first_seen))
        .order_by(func.date(Session.first_seen))
    )

    sessions_by_day = [
        DailyStats(
            date=str(row.date),
            sessions=row.sessions,
            pageviews=0,
            unique_visitors=1,
        )
        for row in daily_result.all()
    ]

    # Pages visited by this IP (top 50)
    pages_result = await db.execute(
        select(
            Event.page_url,
            func.count(Event.id).label("pageviews"),
        )
        .join(Session, Event.session_id == Session.id)
        .where(
            Session.ip_address == ip_address,
            Session.first_seen >= start,
            Event.event_type == "pageview",
            Event.page_url.isnot(None),
        )
        .group_by(Event.page_url)
        .order_by(func.count(Event.id).desc())
        .limit(50)
    )
    pages = [
        IPPageStats(page_url=row.page_url, pageviews=row.pageviews) for row in pages_result.all()
    ]

    # Events by type for this IP (excluding pageviews)
    events_by_type_result = await db.execute(
        select(
            Event.event_type,
            func.count(Event.id).label("event_count"),
        )
        .join(Session, Event.session_id == Session.id)
        .where(
            Session.ip_address == ip_address,
            Session.first_seen >= start,
            Event.event_type != "pageview",
        )
        .group_by(Event.event_type)
        .order_by(func.count(Event.id).desc())
        .limit(50)
    )
    events = [
        IPEventStats(event_type=row.event_type, count=row.event_count)
        for row in events_by_type_result.all()
    ]

    return IPDetailStats(
        ip_address=str(ip_address),
        total_sessions=agg_data.sessions,
        total_pageviews=total_pageviews,
        total_events=total_events,
        countries=[c for c in (agg_data.countries or []) if c],
        cities=[c for c in (agg_data.cities or []) if c],
        browsers=[b for b in (agg_data.browsers or []) if b],
        device_types=[d for d in (agg_data.device_types or []) if d],
        operating_systems=[o for o in (agg_data.operating_systems or []) if o],
        referrers=[r for r in (agg_data.referrers or []) if r],
        first_seen=agg_data.first_seen,
        last_seen=agg_data.last_seen,
        sessions_by_day=sessions_by_day,
        pages=pages,
        events=events,
    )


@router.get("/referrers", response_model=list[ReferrerStats])
async def get_referrer_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[ReferrerStats]:
    """Get statistics by referrer."""
    start, _ = get_date_range(days)

    # Total sessions for percentage calculation
    total_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.first_seen >= start, Session.referrer.isnot(None)
        )
    )
    total_sessions = total_result.scalar() or 1

    # Sessions by referrer
    result = await db.execute(
        select(
            Session.referrer,
            func.count(Session.id).label("sessions"),
        )
        .where(Session.first_seen >= start, Session.referrer.isnot(None))
        .group_by(Session.referrer)
        .order_by(func.count(Session.id).desc())
        .limit(limit)
    )

    return [
        ReferrerStats(
            referrer=row.referrer,
            sessions=row.sessions,
            percentage=round(row.sessions / total_sessions * 100, 2),
        )
        for row in result.all()
    ]


@router.get("/pages", response_model=list[PageStats])
async def get_page_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[PageStats]:
    """Get statistics by page."""
    start, _ = get_date_range(days)

    result = await db.execute(
        select(
            Event.page_url,
            func.count(Event.id).label("pageviews"),
            func.count(func.distinct(Event.session_id)).label("unique_sessions"),
        )
        .join(Session, Event.session_id == Session.id)
        .where(
            Session.first_seen >= start,
            Event.event_type == "pageview",
            Event.page_url.isnot(None),
        )
        .group_by(Event.page_url)
        .order_by(func.count(Event.id).desc())
        .limit(limit)
    )

    return [
        PageStats(
            page_url=row.page_url,
            pageviews=row.pageviews,
            unique_sessions=row.unique_sessions,
        )
        for row in result.all()
    ]


@router.get("/events", response_model=list[EventStats])
async def get_event_stats(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[EventStats]:
    """Get statistics by event type."""
    start, _ = get_date_range(days)

    result = await db.execute(
        select(
            Event.event_type,
            func.count(Event.id).label("event_count"),
            func.count(func.distinct(Event.session_id)).label("unique_sessions"),
        )
        .join(Session, Event.session_id == Session.id)
        .where(Session.first_seen >= start)
        .group_by(Event.event_type)
        .order_by(func.count(Event.id).desc())
        .limit(limit)
    )

    return [
        EventStats(
            event_type=row.event_type,
            count=row.event_count,
            unique_sessions=row.unique_sessions,
        )
        for row in result.all()
    ]


@router.get("/campaigns", response_model=list[CampaignStats])
async def get_campaigns(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[CampaignStats]:
    """Get all campaigns with statistics."""
    query = select(Campaign).order_by(Campaign.created_at.desc()).limit(limit)

    if not include_inactive:
        query = query.where(Campaign.is_active == True)  # noqa: E712

    result = await db.execute(query)
    campaigns = result.scalars().all()

    campaign_stats = []
    for campaign in campaigns:
        # Count pixels
        pixel_count_result = await db.execute(
            select(func.count(Pixel.id)).where(Pixel.campaign_id == campaign.id)
        )
        pixel_count = pixel_count_result.scalar() or 0

        # Total opens
        opens_result = await db.execute(
            select(func.sum(Pixel.open_count)).where(Pixel.campaign_id == campaign.id)
        )
        total_opens = opens_result.scalar() or 0

        campaign_stats.append(
            CampaignStats(
                id=campaign.id,
                name=campaign.name,
                tracking_key=campaign.tracking_key,
                is_active=campaign.is_active,
                click_count=campaign.click_count,
                unique_click_count=campaign.unique_click_count,
                pixel_count=pixel_count,
                total_opens=total_opens,
                created_at=campaign.created_at,
            )
        )

    return campaign_stats


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign_detail(
    campaign_id: UUID,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> CampaignDetail:
    """Get detailed campaign statistics."""
    from fastapi import HTTPException

    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    start, _ = get_date_range(days)

    # Clicks by day
    daily_result = await db.execute(
        select(
            func.date(CampaignClick.clicked_at).label("date"),
            func.count(CampaignClick.id).label("sessions"),
            func.count(func.distinct(CampaignClick.ip_address)).label("unique_visitors"),
        )
        .where(
            CampaignClick.campaign_id == campaign_id,
            CampaignClick.clicked_at >= start,
        )
        .group_by(func.date(CampaignClick.clicked_at))
        .order_by(func.date(CampaignClick.clicked_at))
    )

    clicks_by_day = [
        DailyStats(
            date=str(row.date),
            sessions=row.sessions,
            pageviews=0,
            unique_visitors=row.unique_visitors,
        )
        for row in daily_result.all()
    ]

    # Clicks by country
    total_clicks_result = await db.execute(
        select(func.count(CampaignClick.id)).where(
            CampaignClick.campaign_id == campaign_id,
            CampaignClick.clicked_at >= start,
        )
    )
    total_clicks = total_clicks_result.scalar() or 1

    country_result = await db.execute(
        select(
            CampaignClick.country,
            func.count(CampaignClick.id).label("sessions"),
        )
        .where(
            CampaignClick.campaign_id == campaign_id,
            CampaignClick.clicked_at >= start,
        )
        .group_by(CampaignClick.country)
        .order_by(func.count(CampaignClick.id).desc())
        .limit(10)
    )

    clicks_by_country = [
        CountryStats(
            country=row.country,
            sessions=row.sessions,
            percentage=round(row.sessions / total_clicks * 100, 2),
        )
        for row in country_result.all()
    ]

    return CampaignDetail(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        tracking_key=campaign.tracking_key,
        destination_url=campaign.destination_url,
        is_active=campaign.is_active,
        click_count=campaign.click_count,
        unique_click_count=campaign.unique_click_count,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        clicks_by_day=clicks_by_day,
        clicks_by_country=clicks_by_country,
    )


@router.get("/campaigns/{campaign_id}/pixels", response_model=list[PixelStats])
async def get_campaign_pixels(
    campaign_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:read")),
) -> list[PixelStats]:
    """Get pixels for a campaign."""
    from fastapi import HTTPException

    # Verify campaign exists
    campaign_result = await db.execute(select(Campaign.id).where(Campaign.id == campaign_id))
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = await db.execute(
        select(Pixel)
        .where(Pixel.campaign_id == campaign_id)
        .order_by(Pixel.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return [
        PixelStats(
            id=pixel.id,
            pixel_key=pixel.pixel_key,
            recipient_email=pixel.recipient_email,
            recipient_id=pixel.recipient_id,
            open_count=pixel.open_count,
            first_opened_at=pixel.first_opened_at,
            last_opened_at=pixel.last_opened_at,
            created_at=pixel.created_at,
        )
        for pixel in result.scalars().all()
    ]


class CampaignCreate(BaseModel):
    """Request model for creating a campaign."""

    name: str
    description: str | None = None
    destination_url: str | None = None
    extra_data: dict | None = None


class CampaignResponse(BaseModel):
    """Response model for created campaign."""

    id: UUID
    name: str
    description: str | None
    tracking_key: str
    destination_url: str | None
    is_active: bool
    created_at: datetime


class PixelCreate(BaseModel):
    """Request model for creating a pixel."""

    recipient_email: str | None = None
    recipient_id: str | None = None
    extra_data: dict | None = None


class PixelResponse(BaseModel):
    """Response model for created pixel."""

    id: UUID
    pixel_key: str
    campaign_id: UUID
    recipient_email: str | None
    recipient_id: str | None
    created_at: datetime


class PixelBatchCreate(BaseModel):
    """Request model for creating multiple pixels at once."""

    pixels: list[PixelCreate]


class PixelBatchResponse(BaseModel):
    """Response model for batch pixel creation."""

    campaign_id: UUID
    created_count: int
    pixels: list[PixelResponse]


@router.post("/campaigns", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:write")),
) -> CampaignResponse:
    """Create a new analytics campaign for email tracking."""
    from analytics.services.collector import collector_service

    campaign = await collector_service.create_campaign(
        db=db,
        name=data.name,
        description=data.description,
        destination_url=data.destination_url,
        extra_data=data.extra_data,
    )

    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        tracking_key=campaign.tracking_key,
        destination_url=campaign.destination_url,
        is_active=campaign.is_active,
        created_at=campaign.created_at,
    )


@router.post("/campaigns/{campaign_id}/pixels", response_model=PixelResponse, status_code=201)
async def create_pixel(
    campaign_id: UUID,
    data: PixelCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:write")),
) -> PixelResponse:
    """Create a tracking pixel for an email recipient."""
    from fastapi import HTTPException

    from analytics.services.collector import collector_service

    # Verify campaign exists
    campaign_result = await db.execute(select(Campaign.id).where(Campaign.id == campaign_id))
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    pixel = await collector_service.create_pixel(
        db=db,
        campaign_id=campaign_id,
        recipient_email=data.recipient_email,
        recipient_id=data.recipient_id,
        extra_data=data.extra_data,
    )

    return PixelResponse(
        id=pixel.id,
        pixel_key=pixel.pixel_key,
        campaign_id=pixel.campaign_id,
        recipient_email=pixel.recipient_email,
        recipient_id=pixel.recipient_id,
        created_at=pixel.created_at,
    )


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:write")),
) -> None:
    """Delete an analytics campaign and all its associated data.

    This will cascade delete all pixels and clicks associated with the campaign.
    """
    from fastapi import HTTPException

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    await db.delete(campaign)
    await db.commit()


@router.post(
    "/campaigns/{campaign_id}/pixels/batch",
    response_model=PixelBatchResponse,
    status_code=201,
)
async def create_pixels_batch(
    campaign_id: UUID,
    data: PixelBatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_scopes("analytics:write")),
) -> PixelBatchResponse:
    """Create multiple tracking pixels at once for email campaign recipients."""
    from fastapi import HTTPException

    from analytics.services.collector import collector_service

    # Verify campaign exists
    campaign_result = await db.execute(select(Campaign.id).where(Campaign.id == campaign_id))
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    pixels_response = []
    for pixel_data in data.pixels:
        pixel = await collector_service.create_pixel(
            db=db,
            campaign_id=campaign_id,
            recipient_email=pixel_data.recipient_email,
            recipient_id=pixel_data.recipient_id,
            extra_data=pixel_data.extra_data,
        )
        pixels_response.append(
            PixelResponse(
                id=pixel.id,
                pixel_key=pixel.pixel_key,
                campaign_id=pixel.campaign_id,
                recipient_email=pixel.recipient_email,
                recipient_id=pixel.recipient_id,
                created_at=pixel.created_at,
            )
        )

    return PixelBatchResponse(
        campaign_id=campaign_id,
        created_count=len(pixels_response),
        pixels=pixels_response,
    )
