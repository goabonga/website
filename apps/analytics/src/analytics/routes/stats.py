# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Secured analytics stats API routes."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.auth.dependencies import require_scopes
from analytics.auth.models import User
from analytics.database import get_db
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
