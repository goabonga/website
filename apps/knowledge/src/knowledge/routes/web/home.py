# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Home and dashboard web routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import WebAuthContext
from knowledge.database import get_db
from knowledge.models import Collection, Document, Tenant, TenantMember
from knowledge.services.billing import BillingAPIError, get_billing_client
from knowledge.services.quotas import QuotaService
from knowledge.templating import create_templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web"])
templates = create_templates()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page - redirect to dashboard if logged in."""
    from knowledge.auth.dependencies import get_token_from_cookie

    token = await get_token_from_cookie(request)
    if token:
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse(
        request,
        "pages/home.html",
        {"user": None},
    )


@router.get("/legal", response_class=HTMLResponse)
async def legal(request: Request):
    """Legal notice page."""
    return templates.TemplateResponse(
        request,
        "pages/legal.html",
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    """Privacy policy page."""
    return templates.TemplateResponse(
        request,
        "pages/privacy.html",
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    """Terms of service page."""
    return templates.TemplateResponse(
        request,
        "pages/terms.html",
    )


@router.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    """Public pricing page with plans from billing API."""
    plans = []
    billing_error = None

    try:
        billing_client = get_billing_client()
        if billing_client.is_configured:
            plans = await billing_client.get_plans()
            logger.info(f"Fetched {len(plans)} plans from billing API for public pricing")
        else:
            logger.warning("Billing client not configured, no plans to show")
    except BillingAPIError as e:
        logger.error(f"BillingAPIError: {e}")
        billing_error = str(e)
    except Exception as e:
        logger.error(f"Unexpected error fetching plans: {type(e).__name__}: {e}")
        billing_error = f"Unexpected error: {e}"

    return templates.TemplateResponse(
        request,
        "pages/pricing.html",
        {
            "plans": plans,
            "billing_error": billing_error,
        },
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Main dashboard with stats and recent activity."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    user = auth_result.user
    tenant = auth_result.tenant
    tenant_member = auth_result.tenant_member

    # Get user's tenants for switcher
    result = await db.execute(
        select(Tenant)
        .join(TenantMember, Tenant.id == TenantMember.organization_id)
        .where(TenantMember.user_id == user.id, Tenant.is_active == True)  # noqa: E712
    )
    tenants = result.scalars().all()

    # Stats for current tenant
    collections_count: int = 0
    documents_count: int = 0
    storage_used: int = 0
    recent_collections: list[Any] = []
    usage_stats = None

    if tenant:
        # Count collections
        result = await db.execute(
            select(func.count(Collection.id)).where(Collection.organization_id == tenant.id)
        )
        collections_count = int(result.scalar() or 0)  # type: ignore[arg-type]

        # Count documents
        result = await db.execute(
            select(func.count(Document.id))
            .join(Collection, Document.collection_id == Collection.id)
            .where(Collection.organization_id == tenant.id)
        )
        documents_count = int(result.scalar() or 0)  # type: ignore[arg-type]

        # Recent collections
        result = await db.execute(
            select(Collection)
            .where(Collection.organization_id == tenant.id)
            .order_by(Collection.updated_at.desc())
            .limit(5)
        )
        recent_collections = list(result.scalars().all())

        # Get quota usage
        quota_service = QuotaService(db)
        usage_stats = await quota_service.get_usage(tenant.id)
        storage_used = usage_stats.storage_bytes.current if usage_stats else 0

    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_section": "dashboard",
            "collections_count": collections_count,
            "documents_count": documents_count,
            "storage_used": storage_used,
            "recent_collections": recent_collections,
            "usage_stats": usage_stats,
        },
    )
