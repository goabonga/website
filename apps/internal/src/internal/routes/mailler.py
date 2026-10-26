# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler dashboard routes for HTML pages.

Scopes required:
- mailler:stats - View mailler statistics dashboard
- mailler:read - View emails list and details
"""

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import require_resource_scopes_or_redirect
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services.mailler_client import mailler_client

router = APIRouter(prefix="/mailler", tags=["mailler"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Request mailler scopes for the dashboard
require_mailler_read = require_resource_scopes_or_redirect(
    "mailler", extra_scopes=["vpn:admin", "billing:read"]
)


@router.get("", response_class=HTMLResponse)
async def mailler_dashboard(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    provider: str | None = Query(default=None),
    auth_result: User | RedirectResponse = Depends(require_mailler_read),
):
    """Mailler statistics dashboard."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Mailler dashboard accessed | user_id=%s client_id=%s days=%d provider=%s",
        user.id,
        settings.oauth2_client_id,
        days,
        provider,
    )

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Fetch statistics from mailler service
    stats = await mailler_client.get_stats(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        provider=provider,
    )

    # Get available providers for filter
    providers = await mailler_client.get_providers()

    # Calculate delivery rate and other metrics
    total = stats.get("total", {})
    total_sent = total.get("sent", 0) + total.get("delivered", 0)
    if total_sent > 0:
        delivery_rate = round((total.get("delivered", 0) / total_sent) * 100, 1)
        bounce_rate = round((total.get("bounced", 0) / total_sent) * 100, 1)
        fail_rate = round((total.get("failed", 0) / total_sent) * 100, 1)
    else:
        delivery_rate = 0
        bounce_rate = 0
        fail_rate = 0

    return templates.TemplateResponse(
        request=request,
        name="admin/mailler/dashboard.html",
        context={
            "request": request,
            "active_section": "mailler",
            "user": user,
            "days": days,
            "provider_filter": provider,
            "stats": stats,
            "providers": providers,
            "delivery_rate": delivery_rate,
            "bounce_rate": bounce_rate,
            "fail_rate": fail_rate,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/emails", response_class=HTMLResponse)
async def emails_list(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    auth_result: User | RedirectResponse = Depends(require_mailler_read),
):
    """List all emails with pagination and filters."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Emails list accessed | user_id=%s page=%d provider=%s status=%s",
        user.id,
        page,
        provider,
        status,
    )

    # Fetch emails from mailler service
    emails_data = await mailler_client.get_emails(
        page=page,
        page_size=page_size,
        provider=provider,
        status=status,
    )

    # Get available providers for filter
    providers = await mailler_client.get_providers()

    # Status options for filter
    statuses = ["pending", "queued", "sent", "delivered", "bounced", "failed"]

    return templates.TemplateResponse(
        request=request,
        name="admin/mailler/emails.html",
        context={
            "request": request,
            "active_section": "mailler",
            "user": user,
            "emails": emails_data.get("items", []),
            "total": emails_data.get("total", 0),
            "page": emails_data.get("page", 1),
            "page_size": emails_data.get("page_size", 20),
            "pages": emails_data.get("pages", 1),
            "providers": providers,
            "statuses": statuses,
            "provider_filter": provider,
            "status_filter": status,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/emails/{email_id}", response_class=HTMLResponse)
async def email_detail(
    request: Request,
    email_id: str = Path(..., description="Email UUID"),
    auth_result: User | RedirectResponse = Depends(require_mailler_read),
):
    """View email details."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Validate UUID format
    try:
        UUID(email_id)
    except ValueError:
        return RedirectResponse(
            url="/mailler/emails?error=Invalid+email+ID+format",
            status_code=303,
        )

    logger.info(
        "Email detail accessed | user_id=%s email_id=%s",
        user.id,
        email_id,
    )

    # Fetch email details from mailler service
    email = await mailler_client.get_email(email_id)

    if not email:
        return RedirectResponse(
            url="/mailler/emails?error=Email+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/mailler/email_detail.html",
        context={
            "request": request,
            "active_section": "mailler",
            "user": user,
            "email": email,
            "error": request.query_params.get("error"),
        },
    )
