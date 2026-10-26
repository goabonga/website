# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Analytics dashboard routes for HTML pages.

Scopes required:
- analytics:read - View analytics dashboard and statistics
- analytics:write - Create and delete campaigns
"""

import uuid

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services.analytics_client import analytics_client

router = APIRouter(prefix="/analytics", tags=["analytics"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Use resource-level scope request to get all permissions at once for proper UI display
# Also request vpn:admin to show VPN link in navigation if user has permission
require_analytics_read = require_resource_scopes_or_redirect(
    "analytics", extra_scopes=["vpn:admin", "billing:read"]
)
require_analytics_write = require_scope_or_redirect("analytics:write")
require_analytics_delete = require_scope_or_redirect("analytics:delete")


@router.get("", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    auth_result: User | RedirectResponse = Depends(require_analytics_read),
):
    """Analytics overview dashboard."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Analytics dashboard accessed | user_id=%s client_id=%s days=%d",
        user.id,
        settings.oauth2_client_id,
        days,
    )

    # Fetch overview statistics
    overview = await analytics_client.get_overview(days=days)
    daily_stats = await analytics_client.get_daily_stats(days=days)
    country_stats = await analytics_client.get_country_stats(days=days, limit=10)
    device_stats = await analytics_client.get_device_stats(days=days)
    browser_stats = await analytics_client.get_browser_stats(days=days, limit=10)
    referrer_stats = await analytics_client.get_referrer_stats(days=days, limit=10)
    page_stats = await analytics_client.get_page_stats(days=days, limit=20)
    event_stats = await analytics_client.get_event_stats(days=days, limit=20)
    ip_stats = await analytics_client.get_ip_stats(days=days, limit=10)

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/dashboard.html",
        context={
            "request": request,
            "active_section": "analytics",
            "user": user,
            "days": days,
            "overview": overview,
            "daily_stats": daily_stats,
            "country_stats": country_stats,
            "device_stats": device_stats,
            "browser_stats": browser_stats,
            "referrer_stats": referrer_stats,
            "page_stats": page_stats,
            "event_stats": event_stats,
            "ip_stats": ip_stats,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_list(
    request: Request,
    include_inactive: bool = Query(default=False),
    auth_result: User | RedirectResponse = Depends(require_analytics_read),
):
    """List all marketing campaigns."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Campaigns list accessed | user_id=%s client_id=%s include_inactive=%s",
        user.id,
        settings.oauth2_client_id,
        include_inactive,
    )

    campaigns = await analytics_client.get_campaigns(include_inactive=include_inactive)

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/campaigns.html",
        context={
            "request": request,
            "active_section": "analytics",
            "user": user,
            "campaigns": campaigns,
            "include_inactive": include_inactive,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(
    request: Request,
    campaign_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    auth_result: User | RedirectResponse = Depends(require_analytics_read),
):
    """View detailed campaign statistics."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Campaign detail accessed | user_id=%s client_id=%s campaign_id=%s days=%d",
        user.id,
        settings.oauth2_client_id,
        campaign_id,
        days,
    )

    campaign = await analytics_client.get_campaign_detail(campaign_id, days=days)

    if not campaign:
        return RedirectResponse(
            url="/analytics/campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Get pixels for this campaign
    pixels = await analytics_client.get_campaign_pixels(campaign_id, limit=100)

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/campaign_detail.html",
        context={
            "request": request,
            "active_section": "analytics",
            "user": user,
            "campaign": campaign,
            "pixels": pixels,
            "days": days,
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/campaigns/{campaign_id}/delete")
async def campaign_delete(
    request: Request,
    campaign_id: uuid.UUID,
    auth_result: User | RedirectResponse = Depends(require_analytics_write),
):
    """Delete an analytics campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    success = await analytics_client.delete_campaign(campaign_id)

    if not success:
        logger.warning(
            "Failed to delete analytics campaign | user_id=%s campaign_id=%s",
            user.id,
            campaign_id,
        )
        return RedirectResponse(
            url=f"/analytics/campaigns/{campaign_id}?error=Failed+to+delete+campaign",
            status_code=303,
        )

    logger.info(
        "Analytics campaign deleted | user_id=%s campaign_id=%s",
        user.id,
        campaign_id,
    )

    return RedirectResponse(
        url="/analytics/campaigns?success=Campaign+deleted+successfully",
        status_code=303,
    )


@router.post("/campaigns/bulk-delete")
async def campaigns_bulk_delete(
    request: Request,
    campaign_ids: list[str] = Form(...),
    auth_result: User | RedirectResponse = Depends(require_analytics_write),
):
    """Delete multiple analytics campaigns."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Convert string IDs to UUIDs
    try:
        uuids = [uuid.UUID(cid) for cid in campaign_ids]
    except ValueError:
        return RedirectResponse(
            url="/analytics/campaigns?error=Invalid+campaign+ID+format",
            status_code=303,
        )

    if not uuids:
        return RedirectResponse(
            url="/analytics/campaigns?error=No+campaigns+selected",
            status_code=303,
        )

    deleted, failed = await analytics_client.delete_campaigns_bulk(uuids)

    logger.info(
        "Bulk delete analytics campaigns | user_id=%s deleted=%d failed=%d",
        user.id,
        deleted,
        failed,
    )

    if failed > 0:
        return RedirectResponse(
            url=f"/analytics/campaigns?success=Deleted+{deleted}+campaigns,+{failed}+failed",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/analytics/campaigns?success=Deleted+{deleted}+campaigns+successfully",
        status_code=303,
    )


@router.get("/ips", response_class=HTMLResponse)
async def ip_stats_list(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    auth_result: User | RedirectResponse = Depends(require_analytics_read),
):
    """List IP addresses with their statistics."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "IP stats list accessed | user_id=%s client_id=%s days=%d limit=%d",
        user.id,
        settings.oauth2_client_id,
        days,
        limit,
    )

    ip_stats = await analytics_client.get_ip_stats(days=days, limit=limit)

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/ips.html",
        context={
            "request": request,
            "active_section": "analytics",
            "user": user,
            "ip_stats": ip_stats,
            "days": days,
            "limit": limit,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/ips/{ip_address:path}", response_class=HTMLResponse)
async def ip_detail(
    request: Request,
    ip_address: str,
    days: int = Query(default=30, ge=1, le=365),
    auth_result: User | RedirectResponse = Depends(require_analytics_read),
):
    """View detailed statistics for a specific IP address."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "IP detail accessed | user_id=%s client_id=%s ip_address=%s days=%d",
        user.id,
        settings.oauth2_client_id,
        ip_address,
        days,
    )

    ip_detail_stats = await analytics_client.get_ip_detail(ip_address, days=days)

    if not ip_detail_stats:
        return RedirectResponse(
            url="/analytics/ips?error=IP+address+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/ip_detail.html",
        context={
            "request": request,
            "active_section": "analytics",
            "user": user,
            "ip": ip_detail_stats,
            "days": days,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/reset")
async def reset_analytics(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_analytics_delete),
):
    """Reset all analytics data. Requires analytics:delete scope (super_admin only)."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    result = await analytics_client.reset_all_analytics()

    if not result:
        logger.warning(
            "Failed to reset analytics | user_id=%s",
            user.id,
        )
        return RedirectResponse(
            url="/analytics?error=Failed+to+reset+analytics",
            status_code=303,
        )

    logger.info(
        "Analytics reset | user_id=%s sessions=%d events=%d campaigns=%d",
        user.id,
        result.get("sessions_deleted", 0),
        result.get("events_deleted", 0),
        result.get("campaigns_deleted", 0),
    )

    sessions = result.get("sessions_deleted", 0)
    events = result.get("events_deleted", 0)
    campaigns = result.get("campaigns_deleted", 0)

    return RedirectResponse(
        url=f"/analytics?success=Reset+complete:+{sessions}+sessions,+{events}+events,+{campaigns}+campaigns+deleted",
        status_code=303,
    )
