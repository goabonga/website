# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organization management web routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import (
    ACTIVE_TENANT_COOKIE,
    get_web_auth_context,
)
from knowledge.auth.models import WebAuthContext
from knowledge.database import get_db
from knowledge.logging import get_logger
from knowledge.models import (
    Organization,
    OrganizationMember,
)
from knowledge.services.billing import BillingAPIError, checkout_redirect_urls, get_billing_client
from knowledge.services.quotas import QuotaService
from knowledge.templating import create_templates

logger = get_logger(__name__)
router = APIRouter(tags=["web-organizations"])
templates = create_templates()


async def _get_common_context(
    request: Request,
    db: AsyncSession,
    auth_result: WebAuthContext,
    active_section: str = "organization_settings",
) -> dict:
    """Get common template context."""
    user = auth_result.user
    organization = auth_result.tenant  # Using tenant alias for backward compat

    # Get user's organizations for switcher
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id, Organization.is_active == True)  # noqa: E712
    )
    organizations = result.scalars().all()

    return {
        "user": user,
        "tenant": organization,  # Backward compat
        "organization": organization,
        "tenant_member": auth_result.tenant_member,  # Backward compat
        "organization_member": auth_result.tenant_member,
        "tenants": organizations,  # Backward compat
        "organizations": organizations,
        "active_section": active_section,
    }


@router.post("/switch")
async def switch_organization(
    request: Request,
    tenant_id: UUID = Form(None),  # Backward compat
    organization_id: UUID = Form(None),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Switch active organization."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    user = auth_result.user

    # Support both parameter names
    org_id = organization_id or tenant_id
    if not org_id:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Verify user is member of this organization
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Set cookie and redirect
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=ACTIVE_TENANT_COOKIE,  # Keep cookie name for backward compat
        value=str(org_id),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days
    )
    return response


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Pricing page with plan comparison."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant
    current_plan = organization.plan.value
    current_price_id = None
    current_billing_period = "monthly"  # Default to monthly

    # Fetch plans from billing API
    plans = []
    billing_error = None
    try:
        billing_client = get_billing_client()
        if billing_client.is_configured:
            plans = await billing_client.get_plans()
            logger.info(f"Fetched {len(plans)} plans from billing API")

            # Get current subscription to determine billing period
            subscription = await billing_client.get_tenant_subscription(str(organization.id))
            if subscription and subscription.price_id:
                current_price_id = subscription.price_id
                # Find the billing period from the price
                for plan in plans:
                    for price in plan.prices:
                        if price.id == current_price_id:
                            current_billing_period = (
                                "yearly" if price.interval == "year" else "monthly"
                            )
                            break
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
        "tenants/pricing.html",
        {
            **(await _get_common_context(request, db, auth_result, "pricing")),
            "current_plan": current_plan,
            "current_price_id": current_price_id,
            "current_billing_period": current_billing_period,
            "plans": plans,
            "billing_error": billing_error,
        },
    )


@router.post("/checkout")
async def checkout(
    request: Request,
    price_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Create a Stripe Checkout session and redirect to payment."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant

    try:
        billing_client = get_billing_client()
        if not billing_client.is_configured:
            return RedirectResponse(
                url="/organizations/pricing?error=billing_not_configured",
                status_code=302,
            )
        success_url, cancel_url = checkout_redirect_urls()

        # Determine customer name: use user's name for personal workspaces,
        # organization name for real organizations
        is_personal_workspace = organization.name.endswith("'s Workspace")
        if is_personal_workspace and auth_result.user and auth_result.user.name:
            customer_name = auth_result.user.name
        else:
            customer_name = organization.name

        # Create checkout session (with customer info for auto-creation if not exists)
        session = await billing_client.create_checkout_session(
            tenant_id=str(organization.id),
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=auth_result.user.email if auth_result.user else None,
            customer_name=customer_name,
        )

        # Redirect to Stripe Checkout
        return RedirectResponse(url=session.url, status_code=303)

    except BillingAPIError as e:
        logger.error(f"Checkout error: {e}")
        return RedirectResponse(
            url=f"/organizations/pricing?error={str(e)}",
            status_code=302,
        )


@router.get("/upgrade/preview")
async def upgrade_preview(
    request: Request,
    price_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Get proration preview for upgrading to a new plan.

    Returns JSON with proration details for display before confirming upgrade.
    """
    if isinstance(auth_result, RedirectResponse):
        return {"error": "Not authenticated"}

    if not auth_result.tenant:
        return {"error": "No organization selected"}

    organization = auth_result.tenant

    try:
        billing_client = get_billing_client()
        if not billing_client.is_configured:
            return {"error": "Billing not configured"}

        # Get current subscription
        subscription = await billing_client.get_tenant_subscription(str(organization.id))
        if not subscription:
            return {"error": "No active subscription found", "has_subscription": False}

        # Get proration preview
        preview = await billing_client.preview_upgrade(
            subscription_id=subscription.id,
            new_price_id=price_id,
        )

        return {
            "success": True,
            "subscription_id": subscription.id,
            "current_plan_name": preview.current_plan_name,
            "new_plan_name": preview.new_plan_name,
            "current_price_amount": preview.current_price_amount,
            "new_price_amount": preview.new_price_amount,
            "line_items": [
                {
                    "description": item.description,
                    "amount": item.amount,
                    "display_amount": item.display_amount,
                }
                for item in preview.line_items
            ],
            "subtotal": preview.subtotal,
            "total": preview.total,
            "display_total": preview.display_total,
            "credit_applied": preview.credit_applied,
            "display_credit": preview.display_credit,
            "currency": preview.currency,
        }

    except BillingAPIError as e:
        logger.error(f"Upgrade preview error: {e}")
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected upgrade preview error: {type(e).__name__}: {e}")
        return {"error": f"Unexpected error: {e}"}


@router.post("/upgrade")
async def upgrade_plan(
    request: Request,
    price_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Upgrade to a new plan with proration."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant

    try:
        billing_client = get_billing_client()
        if not billing_client.is_configured:
            return RedirectResponse(
                url="/organizations/pricing?error=billing_not_configured",
                status_code=302,
            )

        # Get current subscription
        subscription = await billing_client.get_tenant_subscription(str(organization.id))
        if not subscription:
            # No subscription - create checkout session for new subscription
            success_url, cancel_url = checkout_redirect_urls()

            is_personal_workspace = organization.name.endswith("'s Workspace")
            if is_personal_workspace and auth_result.user and auth_result.user.name:
                customer_name = auth_result.user.name
            else:
                customer_name = organization.name

            session = await billing_client.create_checkout_session(
                tenant_id=str(organization.id),
                price_id=price_id,
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=auth_result.user.email if auth_result.user else None,
                customer_name=customer_name,
            )
            return RedirectResponse(url=session.url, status_code=303)

        # Perform upgrade with proration
        result = await billing_client.upgrade_subscription(
            subscription_id=subscription.id,
            new_price_id=price_id,
            proration_behavior="create_prorations",
        )

        if result.success:
            return RedirectResponse(
                url="/organizations/pricing?success=true&upgraded=true",
                status_code=302,
            )
        else:
            return RedirectResponse(
                url="/organizations/pricing?error=upgrade_failed",
                status_code=302,
            )

    except BillingAPIError as e:
        logger.error(f"Upgrade error: {e}")
        return RedirectResponse(
            url=f"/organizations/pricing?error={str(e)}",
            status_code=302,
        )


@router.get("/settings", response_class=HTMLResponse)
async def organization_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Organization settings page."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Only admins and owners can access settings
    if not auth_result.is_tenant_admin:
        return templates.TemplateResponse(
            request,
            "errors/403.html",
            {
                "user": auth_result.user,
                "required_scope": "organization:admin",
            },
            status_code=403,
        )

    organization = auth_result.tenant

    # Get usage stats
    quota_service = QuotaService(db)
    usage_stats = await quota_service.get_usage(organization.id)

    return templates.TemplateResponse(
        request,
        "tenants/settings.html",  # Keep template path for now
        {
            **(await _get_common_context(request, db, auth_result, "organization_settings")),
            "usage_stats": usage_stats,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def update_organization_settings(
    request: Request,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Update organization settings."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    if not auth_result.is_tenant_admin:
        return templates.TemplateResponse(
            request,
            "errors/403.html",
            {
                "user": auth_result.user,
                "required_scope": "organization:admin",
            },
            status_code=403,
        )

    organization = auth_result.tenant
    organization.name = name
    await db.commit()

    return RedirectResponse(url="/organizations/settings", status_code=302)
