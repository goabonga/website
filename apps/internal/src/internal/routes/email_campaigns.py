# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email Campaigns CRUD routes for sending emails.

Scopes required:
- email_campaigns:read - View email campaigns
- email_campaigns:write - Create, update email campaigns
- email_campaigns:send - Send/pause campaigns
- email_campaigns:delete - Delete email campaigns
"""

import contextlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import (
    require_resource_scopes_or_redirect,
    require_scope_or_redirect,
)
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services import mailler_client
from internal.services.mailler_client import MaillerAPIError

router = APIRouter(prefix="/email-campaigns", tags=["email-campaigns"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)


def parse_datetime_fields(item: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Parse ISO datetime strings to datetime objects for template rendering."""
    for field in fields:
        if field in item and item[field] and isinstance(item[field], str):
            with contextlib.suppress(ValueError, AttributeError):
                item[field] = datetime.fromisoformat(item[field].replace("Z", "+00:00"))
    return item


def parse_campaigns(campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in campaign list."""
    datetime_fields = ["created_at", "updated_at", "scheduled_at", "started_at", "completed_at"]
    return [parse_datetime_fields(c, datetime_fields) for c in campaigns]


def parse_sends(sends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse datetime fields in send list."""
    datetime_fields = [
        "created_at",
        "queued_at",
        "sent_at",
        "delivered_at",
        "opened_at",
        "clicked_at",
        "bounced_at",
    ]
    return [parse_datetime_fields(s, datetime_fields) for s in sends]


# Campaign statuses (keep for template rendering)
CAMPAIGN_STATUSES = ["draft", "scheduled", "sending", "paused", "completed", "failed"]
SEND_STATUSES = [
    "pending",
    "queued",
    "sent",
    "delivered",
    "opened",
    "clicked",
    "bounced",
    "complained",
    "failed",
]

# Scope dependencies
require_read = require_resource_scopes_or_redirect(
    "email_campaigns", extra_scopes=["vpn:admin", "billing:read"]
)
require_write = require_scope_or_redirect("email_campaigns:write")
require_send = require_scope_or_redirect("email_campaigns:send")
require_delete = require_scope_or_redirect("email_campaigns:delete")


@router.get("", response_class=HTMLResponse)
async def email_campaigns_list(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None),
    status: str | None = Query(None),
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """List all email campaigns with pagination and filtering."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Email campaigns list accessed | user_id=%s page=%d search=%s status=%s",
        user.id,
        page,
        search,
        status,
    )

    limit = 20

    # Get campaigns from mailler API
    result = await mailler_client.get_campaigns(
        page=page,
        page_size=limit,
        status=status,
        search=search,
    )

    # Parse datetime strings for template rendering
    campaigns = parse_campaigns(result.get("items", []))
    total = result.get("total", 0)
    total_pages = result.get("pages", 1)

    return templates.TemplateResponse(
        request=request,
        name="admin/email_campaigns/list.html",
        context={
            "request": request,
            "active_section": "email_campaigns",
            "user": user,
            "campaigns": campaigns,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search,
            "status_filter": status,
            "statuses": CAMPAIGN_STATUSES,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def email_campaign_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to create a new email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info("Email campaign new form accessed | user_id=%s", user.id)

    # Get only active templates from mailler API
    templates_result = await mailler_client.get_templates(page=1, page_size=100, status="active")
    email_templates = templates_result.get("items", [])

    # Get contact groups from mailler API
    groups_result = await mailler_client.get_contact_groups(page=1, page_size=100)
    contact_groups = groups_result.get("items", [])

    # Get available email providers from Mailler API
    email_providers = await mailler_client.get_providers()

    return templates.TemplateResponse(
        request=request,
        name="admin/email_campaigns/form.html",
        context={
            "request": request,
            "active_section": "email_campaigns",
            "user": user,
            "campaign": None,
            "is_edit": False,
            "email_templates": email_templates,
            "contact_groups": contact_groups,
            "email_providers": email_providers,
            "statuses": CAMPAIGN_STATUSES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/new")
async def email_campaign_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    template_id: int = Form(...),
    group_id: int = Form(...),
    provider: str = Form(""),
    from_name: str = Form(""),
    from_email: str = Form(""),
    reply_to: str = Form(""),
    scheduled_at: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Create a new email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    name = name.strip()
    description = description.strip()

    # Create campaign via mailler API
    campaign_data = {
        "name": name,
        "description": description or None,
        "template_id": template_id,
        "group_id": group_id,
        "provider": provider.strip() or None,
        "from_name": from_name.strip() or None,
        "from_email": from_email.strip() or None,
        "reply_to": reply_to.strip() or None,
    }

    if scheduled_at:
        campaign_data["scheduled_at"] = scheduled_at

    result = await mailler_client.create_campaign(campaign_data)

    if not result:
        return RedirectResponse(
            url="/email-campaigns/new?error=Failed+to+create+campaign",
            status_code=303,
        )

    campaign_id = result.get("id")

    logger.info(
        "Email campaign created | user_id=%s campaign_id=%s name=%s",
        auth_result.id,
        campaign_id,
        name,
    )

    return RedirectResponse(
        url=f"/email-campaigns/{campaign_id}?success=Campaign+created+successfully",
        status_code=303,
    )


@router.post("/bulk-delete")
async def email_campaigns_bulk_delete(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete multiple email campaigns at once."""
    if not isinstance(auth_result, User):
        return auth_result

    form = await request.form()
    campaign_ids_raw = form.getlist("campaign_ids")

    if not campaign_ids_raw:
        return RedirectResponse(
            url="/email-campaigns?error=No+campaigns+selected",
            status_code=303,
        )

    try:
        campaign_ids = [int(str(id_str)) for id_str in campaign_ids_raw if id_str]
    except ValueError:
        return RedirectResponse(
            url="/email-campaigns?error=Invalid+campaign+IDs",
            status_code=303,
        )

    if not campaign_ids:
        return RedirectResponse(
            url="/email-campaigns?error=No+campaigns+selected",
            status_code=303,
        )

    deleted_count = 0
    skipped_count = 0

    for cid in campaign_ids:
        # Get campaign to check status
        campaign = await mailler_client.get_campaign(cid)
        if not campaign:
            continue

        # Can't delete campaigns that are currently sending
        if campaign.get("status") == "sending":
            skipped_count += 1
            continue

        if await mailler_client.delete_campaign(cid):
            deleted_count += 1

    logger.info(
        "Bulk delete campaigns | user_id=%s deleted=%d skipped=%d",
        auth_result.id,
        deleted_count,
        skipped_count,
    )

    if skipped_count > 0:
        return RedirectResponse(
            url=f"/email-campaigns?success=Deleted+{deleted_count}+campaign(s).+Skipped+{skipped_count}+sending+campaign(s).",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/email-campaigns?success=Deleted+{deleted_count}+campaign(s)+successfully",
        status_code=303,
    )


@router.get("/{campaign_id}", response_class=HTMLResponse)
async def email_campaign_detail(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """View email campaign detail with statistics."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Parse datetime fields for template rendering
    datetime_fields = ["created_at", "updated_at", "scheduled_at", "started_at", "completed_at"]
    campaign = parse_datetime_fields(campaign, datetime_fields)

    # Flatten stats into campaign dict for template access
    if "stats" in campaign and isinstance(campaign["stats"], dict):
        campaign.update(campaign["stats"])

    logger.info(
        "Email campaign detail accessed | user_id=%s campaign_id=%s",
        user.id,
        campaign_id,
    )

    # Get recent sends for this campaign from mailler API
    sends_result = await mailler_client.get_campaign_sends(campaign_id, page=1, page_size=50)
    recent_sends = parse_sends(sends_result.get("items", []))

    # Build status counts from campaign data
    status_counts = {
        "pending": campaign.get("pending_count", 0),
        "queued": campaign.get("queued_count", 0),
        "sent": campaign.get("sent_count", 0),
        "delivered": campaign.get("delivered_count", 0),
        "opened": campaign.get("opened_count", 0),
        "clicked": campaign.get("clicked_count", 0),
        "bounced": campaign.get("bounced_count", 0),
        "complained": campaign.get("complained_count", 0),
        "failed": campaign.get("failed_count", 0),
    }

    return templates.TemplateResponse(
        request=request,
        name="admin/email_campaigns/detail.html",
        context={
            "request": request,
            "active_section": "email_campaigns",
            "user": user,
            "campaign": campaign,
            "recent_sends": recent_sends,
            "status_counts": status_counts,
            "send_statuses": SEND_STATUSES,
            "default_provider": settings.mailler_default_provider,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{campaign_id}/edit", response_class=HTMLResponse)
async def email_campaign_edit(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Show form to edit an email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Can't edit campaigns that are sending or completed
    if campaign.get("status") in ["sending", "completed"]:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Cannot+edit+campaign+in+this+status",
            status_code=303,
        )

    # Parse datetime fields for template rendering
    datetime_fields = ["created_at", "updated_at", "scheduled_at", "started_at", "completed_at"]
    campaign = parse_datetime_fields(campaign, datetime_fields)

    logger.info(
        "Email campaign edit form accessed | user_id=%s campaign_id=%s",
        user.id,
        campaign_id,
    )

    # Get only active templates from mailler API
    templates_result = await mailler_client.get_templates(page=1, page_size=100, status="active")
    email_templates = templates_result.get("items", [])

    # Get contact groups from mailler API
    groups_result = await mailler_client.get_contact_groups(page=1, page_size=100)
    contact_groups = groups_result.get("items", [])

    # Get available email providers from Mailler API
    email_providers = await mailler_client.get_providers()

    return templates.TemplateResponse(
        request=request,
        name="admin/email_campaigns/form.html",
        context={
            "request": request,
            "active_section": "email_campaigns",
            "user": user,
            "campaign": campaign,
            "is_edit": True,
            "email_templates": email_templates,
            "contact_groups": contact_groups,
            "email_providers": email_providers,
            "statuses": CAMPAIGN_STATUSES,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{campaign_id}/edit")
async def email_campaign_update(
    request: Request,
    campaign_id: int,
    name: str = Form(...),
    description: str = Form(""),
    template_id: int = Form(...),
    group_id: int = Form(...),
    provider: str = Form(""),
    from_name: str = Form(""),
    from_email: str = Form(""),
    reply_to: str = Form(""),
    scheduled_at: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_write),
):
    """Update an email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Can't edit campaigns that are sending or completed
    if campaign.get("status") in ["sending", "completed"]:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Cannot+edit+campaign+in+this+status",
            status_code=303,
        )

    name = name.strip()
    description = description.strip()

    # Update campaign via mailler API
    update_data = {
        "name": name,
        "description": description or None,
        "template_id": template_id,
        "group_id": group_id,
        "provider": provider.strip() or None,
        "from_name": from_name.strip() or None,
        "from_email": from_email.strip() or None,
        "reply_to": reply_to.strip() or None,
        "scheduled_at": scheduled_at if scheduled_at else None,
    }

    result = await mailler_client.update_campaign(campaign_id, update_data)

    if not result:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}/edit?error=Failed+to+update+campaign",
            status_code=303,
        )

    logger.info(
        "Email campaign updated | user_id=%s campaign_id=%s",
        auth_result.id,
        campaign_id,
    )

    return RedirectResponse(
        url=f"/email-campaigns/{campaign_id}?success=Campaign+updated+successfully",
        status_code=303,
    )


@router.post("/{campaign_id}/send")
async def email_campaign_send(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_send),
):
    """Start sending an email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Can only send from draft or scheduled status
    if campaign.get("status") not in ["draft", "scheduled"]:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Campaign+cannot+be+sent+in+current+status",
            status_code=303,
        )

    # Send campaign via mailler API (it validates template, group, and recipients)
    try:
        result = await mailler_client.send_campaign(campaign_id)
    except MaillerAPIError as e:
        error_msg = e.message.replace(" ", "+")
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error={error_msg}",
            status_code=303,
        )

    logger.info(
        "Email campaign send started | user_id=%s campaign_id=%s recipients=%d",
        auth_result.id,
        campaign_id,
        result.get("total_recipients", 0),
    )

    return RedirectResponse(
        url=f"/email-campaigns/{campaign_id}?success=Campaign+sending+started",
        status_code=303,
    )


@router.post("/{campaign_id}/pause")
async def email_campaign_pause(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_send),
):
    """Pause a sending campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    if campaign.get("status") != "sending":
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Campaign+is+not+currently+sending",
            status_code=303,
        )

    # Pause campaign via mailler API
    result = await mailler_client.pause_campaign(campaign_id)

    if not result:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Failed+to+pause+campaign",
            status_code=303,
        )

    logger.info(
        "Email campaign paused | user_id=%s campaign_id=%s",
        auth_result.id,
        campaign_id,
    )

    return RedirectResponse(
        url=f"/email-campaigns/{campaign_id}?success=Campaign+paused",
        status_code=303,
    )


@router.post("/{campaign_id}/resume")
async def email_campaign_resume(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_send),
):
    """Resume a paused campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    if campaign.get("status") != "paused":
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Campaign+is+not+paused",
            status_code=303,
        )

    # Resume campaign via mailler API
    result = await mailler_client.resume_campaign(campaign_id)

    if not result:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Failed+to+resume+campaign",
            status_code=303,
        )

    logger.info(
        "Email campaign resumed | user_id=%s campaign_id=%s",
        auth_result.id,
        campaign_id,
    )

    return RedirectResponse(
        url=f"/email-campaigns/{campaign_id}?success=Campaign+resumed",
        status_code=303,
    )


@router.post("/{campaign_id}/delete")
async def email_campaign_delete(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_delete),
):
    """Delete an email campaign."""
    if not isinstance(auth_result, User):
        return auth_result

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return RedirectResponse(
            url="/email-campaigns?error=Campaign+not+found",
            status_code=303,
        )

    # Can't delete campaigns that are currently sending
    if campaign.get("status") == "sending":
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Cannot+delete+campaign+while+sending",
            status_code=303,
        )

    result = await mailler_client.delete_campaign(campaign_id)

    if not result:
        return RedirectResponse(
            url=f"/email-campaigns/{campaign_id}?error=Failed+to+delete+campaign",
            status_code=303,
        )

    logger.info(
        "Email campaign deleted | user_id=%s campaign_id=%s",
        auth_result.id,
        campaign_id,
    )

    return RedirectResponse(
        url="/email-campaigns?success=Campaign+deleted+successfully",
        status_code=303,
    )


@router.get("/{campaign_id}/stats", response_class=JSONResponse)
async def email_campaign_stats(
    request: Request,
    campaign_id: int,
    auth_result: User | RedirectResponse = Depends(require_read),
):
    """Get campaign statistics as JSON (for AJAX updates)."""
    if not isinstance(auth_result, User):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    campaign = await mailler_client.get_campaign(campaign_id)

    if not campaign:
        return JSONResponse({"error": "Campaign not found"}, status_code=404)

    # Stats are nested under 'stats' key in mailler API response
    stats = campaign.get("stats", {})

    return JSONResponse(
        {
            "id": campaign.get("id"),
            "status": campaign.get("status"),
            "total_recipients": stats.get("total_recipients", 0),
            "sent_count": stats.get("sent_count", 0),
            "delivered_count": stats.get("delivered_count", 0),
            "opened_count": stats.get("opened_count", 0),
            "clicked_count": stats.get("clicked_count", 0),
            "bounced_count": stats.get("bounced_count", 0),
            "complained_count": stats.get("complained_count", 0),
            "failed_count": stats.get("failed_count", 0),
            "progress_percent": stats.get("progress_percent", 0),
            "open_rate": stats.get("open_rate", 0),
            "click_rate": stats.get("click_rate", 0),
            "bounce_rate": stats.get("bounce_rate", 0),
            "complaint_rate": stats.get("complaint_rate", 0),
        }
    )
