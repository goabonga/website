# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin routes for statistics."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext, require_scopes
from custom_domain.config import settings
from custom_domain.database import get_db
from custom_domain.logging import get_logger
from custom_domain.models import AuthorizedClient, CustomDomain, DomainStatus, NginxTemplate

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/stats", tags=["admin-stats"])

ADMIN_SCOPES = (settings.admin_scope, f"{settings.admin_scope}:stats")


class DomainStats(BaseModel):
    """Domain statistics."""

    total: int
    active: int
    pending: int
    failed: int
    deleted: int

    # By status breakdown
    by_status: dict[str, int]

    # Time-based
    created_last_24h: int
    created_last_7d: int
    created_last_30d: int
    activated_last_24h: int
    activated_last_7d: int

    # SSL
    ssl_expiring_soon: int  # Within CERTIFICATE_RENEWAL_DAYS
    ssl_expired: int


class ClientStats(BaseModel):
    """Client statistics."""

    total: int
    active: int
    inactive: int


class TemplateStats(BaseModel):
    """Template statistics."""

    total: int
    active: int
    domains_using_custom: int
    domains_using_default: int


class OverviewStats(BaseModel):
    """Overview statistics."""

    domains: DomainStats
    clients: ClientStats
    templates: TemplateStats


class TopClient(BaseModel):
    """Top client by domain count."""

    client_id: str
    name: str
    domain_count: int
    active_count: int


class RecentActivity(BaseModel):
    """Recent activity item."""

    domain: str
    client_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class DashboardResponse(BaseModel):
    """Dashboard response with all stats."""

    overview: OverviewStats
    top_clients: list[TopClient]
    recent_activity: list[RecentActivity]


@router.get("/overview", response_model=OverviewStats)
async def get_overview_stats(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get overview statistics."""
    now = datetime.now(UTC)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    # Domain stats
    total_domains = await db.scalar(select(func.count()).select_from(CustomDomain)) or 0

    deleted_domains = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(CustomDomain.deleted_at.isnot(None))
        )
        or 0
    )

    # Count by status (excluding deleted)
    status_counts = {}
    for status in DomainStatus:
        count = (
            await db.scalar(
                select(func.count())
                .select_from(CustomDomain)
                .where(
                    CustomDomain.status == status,
                    CustomDomain.deleted_at.is_(None),
                )
            )
            or 0
        )
        status_counts[status.value] = count

    # Time-based counts
    created_24h = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(CustomDomain.created_at >= last_24h)
        )
        or 0
    )

    created_7d = (
        await db.scalar(
            select(func.count()).select_from(CustomDomain).where(CustomDomain.created_at >= last_7d)
        )
        or 0
    )

    created_30d = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(CustomDomain.created_at >= last_30d)
        )
        or 0
    )

    activated_24h = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.status == DomainStatus.ACTIVE,
                CustomDomain.ssl_provisioned_at >= last_24h,
                CustomDomain.deleted_at.is_(None),
            )
        )
        or 0
    )

    activated_7d = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.status == DomainStatus.ACTIVE,
                CustomDomain.ssl_provisioned_at >= last_7d,
                CustomDomain.deleted_at.is_(None),
            )
        )
        or 0
    )

    # SSL stats
    ssl_expiring = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.status == DomainStatus.ACTIVE,
                CustomDomain.deleted_at.is_(None),
                CustomDomain.ssl_expires_at.isnot(None),
                CustomDomain.ssl_expires_at
                <= now + timedelta(days=settings.certificate_renewal_days),
                CustomDomain.ssl_expires_at > now,
            )
        )
        or 0
    )

    ssl_expired = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.status == DomainStatus.ACTIVE,
                CustomDomain.deleted_at.is_(None),
                CustomDomain.ssl_expires_at.isnot(None),
                CustomDomain.ssl_expires_at <= now,
            )
        )
        or 0
    )

    domain_stats = DomainStats(
        total=total_domains,
        active=status_counts.get(DomainStatus.ACTIVE.value, 0),
        pending=status_counts.get(DomainStatus.PENDING.value, 0)
        + status_counts.get(DomainStatus.DNS_VERIFYING.value, 0)
        + status_counts.get(DomainStatus.DNS_VERIFIED.value, 0)
        + status_counts.get(DomainStatus.SSL_PROVISIONING.value, 0),
        failed=status_counts.get(DomainStatus.FAILED.value, 0),
        deleted=deleted_domains,
        by_status=status_counts,
        created_last_24h=created_24h,
        created_last_7d=created_7d,
        created_last_30d=created_30d,
        activated_last_24h=activated_24h,
        activated_last_7d=activated_7d,
        ssl_expiring_soon=ssl_expiring,
        ssl_expired=ssl_expired,
    )

    # Client stats
    total_clients = await db.scalar(select(func.count()).select_from(AuthorizedClient)) or 0

    active_clients = (
        await db.scalar(
            select(func.count())
            .select_from(AuthorizedClient)
            .where(AuthorizedClient.is_active == True)  # noqa: E712
        )
        or 0
    )

    client_stats = ClientStats(
        total=total_clients,
        active=active_clients,
        inactive=total_clients - active_clients,
    )

    # Template stats
    total_templates = await db.scalar(select(func.count()).select_from(NginxTemplate)) or 0

    active_templates = (
        await db.scalar(
            select(func.count()).select_from(NginxTemplate).where(NginxTemplate.is_active == True)  # noqa: E712
        )
        or 0
    )

    domains_with_custom = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.nginx_template_id.isnot(None),
                CustomDomain.deleted_at.is_(None),
            )
        )
        or 0
    )

    domains_with_default = (
        await db.scalar(
            select(func.count())
            .select_from(CustomDomain)
            .where(
                CustomDomain.nginx_template_id.is_(None),
                CustomDomain.deleted_at.is_(None),
            )
        )
        or 0
    )

    template_stats = TemplateStats(
        total=total_templates,
        active=active_templates,
        domains_using_custom=domains_with_custom,
        domains_using_default=domains_with_default,
    )

    return OverviewStats(
        domains=domain_stats,
        clients=client_stats,
        templates=template_stats,
    )


@router.get("/top-clients", response_model=list[TopClient])
async def get_top_clients(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get top clients by domain count."""
    # Get all clients with domain counts
    result = await db.execute(select(AuthorizedClient).order_by(AuthorizedClient.name))
    clients = result.scalars().all()

    top_clients = []
    for client in clients:
        total_count = (
            await db.scalar(
                select(func.count())
                .select_from(CustomDomain)
                .where(
                    CustomDomain.client_id == client.client_id,
                    CustomDomain.deleted_at.is_(None),
                )
            )
            or 0
        )

        active_count = (
            await db.scalar(
                select(func.count())
                .select_from(CustomDomain)
                .where(
                    CustomDomain.client_id == client.client_id,
                    CustomDomain.status == DomainStatus.ACTIVE,
                    CustomDomain.deleted_at.is_(None),
                )
            )
            or 0
        )

        if total_count > 0:
            top_clients.append(
                TopClient(
                    client_id=client.client_id,
                    name=client.name,
                    domain_count=total_count,
                    active_count=active_count,
                )
            )

    # Sort by domain count descending
    top_clients.sort(key=lambda x: x.domain_count, reverse=True)

    return top_clients[:limit]


@router.get("/recent-activity", response_model=list[RecentActivity])
async def get_recent_activity(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get recent domain activity."""
    result = await db.execute(
        select(CustomDomain)
        .where(CustomDomain.deleted_at.is_(None))
        .order_by(CustomDomain.updated_at.desc())
        .limit(limit)
    )
    domains = result.scalars().all()

    return [
        RecentActivity(
            domain=d.domain,
            client_id=d.client_id,
            status=d.status.value,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in domains
    ]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get complete dashboard data."""
    overview = await get_overview_stats(db=db, auth=auth)
    top_clients = await get_top_clients(limit=5, db=db, auth=auth)
    recent = await get_recent_activity(limit=10, db=db, auth=auth)

    return DashboardResponse(
        overview=overview,
        top_clients=top_clients,
        recent_activity=recent,
    )
