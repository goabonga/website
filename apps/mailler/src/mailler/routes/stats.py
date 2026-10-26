# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Statistics routes."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.email import Email, EmailStatus
from mailler.schemas.stats import DailyStatsItem, ProviderStatsItem, StatsResponse

logger = get_logger(__name__)

router = APIRouter(tags=["Stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    start_date: date | None = Query(default=None, description="Start date (inclusive)"),
    end_date: date | None = Query(default=None, description="End date (inclusive)"),
    provider: str | None = Query(default=None, description="Filter by provider"),
    client_id: str | None = Query(
        default=None, description="Administrators only: restrict to one client"
    ),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes("mailler:stats")),
) -> StatsResponse:
    """Get the email sending statistics of the calling client (real-time from emails table).

    Administrators get the statistics of every client, or of the one named by ``client_id``.

    Args:
        start_date: Optional start date (defaults to 30 days ago)
        end_date: Optional end date (defaults to today)
        provider: Optional provider filter
        client_id: Optional client filter, honoured for administrators only
        db: Database session

    Returns:
        Statistics with totals, by-provider, and by-date breakdowns
    """
    # Set defaults
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Convert dates to datetime for comparison
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC)

    # Base query conditions
    base_conditions = [
        Email.created_at >= start_dt,
        Email.created_at <= end_dt,
    ]
    if provider:
        base_conditions.append(Email.provider == provider)

    # Query totals by status
    total_stmt = select(
        func.count(case((Email.status == EmailStatus.SENT.value, 1))).label("sent"),
        func.count(case((Email.status == EmailStatus.DELIVERED.value, 1))).label("delivered"),
        func.count(case((Email.status == EmailStatus.BOUNCED.value, 1))).label("bounced"),
        func.count(case((Email.status == EmailStatus.FAILED.value, 1))).label("failed"),
    ).where(*base_conditions)
    total_stmt = auth.restrict(total_stmt, Email.client_id, client_id)

    total_result = await db.execute(total_stmt)
    total_row = total_result.one()

    # Query by provider
    by_provider_stmt = (
        select(
            Email.provider,
            func.count(case((Email.status == EmailStatus.SENT.value, 1))).label("sent"),
            func.count(case((Email.status == EmailStatus.DELIVERED.value, 1))).label("delivered"),
            func.count(case((Email.status == EmailStatus.BOUNCED.value, 1))).label("bounced"),
            func.count(case((Email.status == EmailStatus.FAILED.value, 1))).label("failed"),
        )
        .where(*base_conditions)
        .group_by(Email.provider)
    )
    by_provider_stmt = auth.restrict(by_provider_stmt, Email.client_id, client_id)

    provider_result = await db.execute(by_provider_stmt)
    provider_rows = provider_result.all()

    # Query by date
    by_date_stmt = (
        select(
            func.date(Email.created_at).label("email_date"),
            func.count(case((Email.status == EmailStatus.SENT.value, 1))).label("sent"),
            func.count(case((Email.status == EmailStatus.DELIVERED.value, 1))).label("delivered"),
            func.count(case((Email.status == EmailStatus.BOUNCED.value, 1))).label("bounced"),
            func.count(case((Email.status == EmailStatus.FAILED.value, 1))).label("failed"),
        )
        .where(*base_conditions)
        .group_by(func.date(Email.created_at))
        .order_by(func.date(Email.created_at))
    )
    by_date_stmt = auth.restrict(by_date_stmt, Email.client_id, client_id)

    date_result = await db.execute(by_date_stmt)
    date_rows = date_result.all()

    # Format response
    total = ProviderStatsItem(
        sent=total_row.sent or 0,
        delivered=total_row.delivered or 0,
        bounced=total_row.bounced or 0,
        failed=total_row.failed or 0,
    )

    provider_stats = {
        row.provider: ProviderStatsItem(
            sent=row.sent or 0,
            delivered=row.delivered or 0,
            bounced=row.bounced or 0,
            failed=row.failed or 0,
        )
        for row in provider_rows
    }

    daily_stats = [
        DailyStatsItem(
            date=row.email_date,
            sent=row.sent or 0,
            delivered=row.delivered or 0,
            bounced=row.bounced or 0,
            failed=row.failed or 0,
        )
        for row in date_rows
    ]

    logger.info(
        "Stats retrieved",
        extra={
            "start_date": str(start_date),
            "end_date": str(end_date),
            "provider": provider,
            "total_sent": total.sent,
        },
    )

    return StatsResponse(
        total=total,
        by_provider=provider_stats,
        by_date=daily_stats,
    )
