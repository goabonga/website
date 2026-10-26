# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Organization management web routes."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import (
    ACTIVE_TENANT_COOKIE,
    get_token_from_cookie,
    get_web_auth_context,
)
from knowledge.auth.models import WebAuthContext
from knowledge.config import get_settings
from knowledge.database import get_db
from knowledge.logging import get_logger
from knowledge.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    WorkspaceDeletionRequest,
)
from knowledge.models.enums import CustomDomainStatus, InvitationStatus, OrganizationMemberRole
from knowledge.models.workspace_deletion_request import DeletionRequestStatus
from knowledge.services import custom_domain as domain_service
from knowledge.services.billing import BillingAPIError, checkout_redirect_urls, get_billing_client
from knowledge.services.custom_domain import CustomDomainError, get_custom_domain_client
from knowledge.services.quotas import QuotaService
from knowledge.tasks import (
    send_workspace_deleted_email,
    send_workspace_deletion_email,
    send_workspace_deletion_scheduled_email,
)
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


@router.post("/delete", response_class=HTMLResponse)
async def delete_organization(
    request: Request,
    confirmation_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Request workspace deletion - sends confirmation email."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant:
        return RedirectResponse(url="/dashboard", status_code=302)

    # Only owner can delete
    if not auth_result.is_tenant_owner:
        return templates.TemplateResponse(
            request,
            "errors/403.html",
            {
                "user": auth_result.user,
                "required_scope": "organization:owner",
            },
            status_code=403,
        )

    organization = auth_result.tenant
    user = auth_result.user

    # Verify confirmation matches organization name
    if confirmation_name.strip() != organization.name:
        # Get usage stats for re-rendering the page
        quota_service = QuotaService(db)
        usage_stats = await quota_service.get_usage(organization.id)

        return templates.TemplateResponse(
            request,
            "tenants/settings.html",
            {
                **(await _get_common_context(request, db, auth_result, "organization_settings")),
                "usage_stats": usage_stats,
                "delete_error": "Organization name does not match. Please type the exact name to confirm deletion.",
            },
        )

    # Cancel any existing pending deletion requests for this organization
    result = await db.execute(
        select(WorkspaceDeletionRequest).where(
            WorkspaceDeletionRequest.organization_id == organization.id,
            WorkspaceDeletionRequest.status == DeletionRequestStatus.PENDING,
        )
    )
    existing_requests = result.scalars().all()
    for req in existing_requests:
        req.cancel()

    # Create new deletion request
    deletion_request = WorkspaceDeletionRequest(
        organization_id=organization.id,
        requested_by=user.id,
        email=user.email,
        token=WorkspaceDeletionRequest.generate_token(),
        expires_at=WorkspaceDeletionRequest.default_expiry(),
    )
    db.add(deletion_request)
    await db.commit()
    await db.refresh(deletion_request)

    # Build confirmation URL
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")
    confirmation_url = f"{base_url}/organizations/delete/confirm/{deletion_request.token}"

    # Send confirmation email
    send_workspace_deletion_email.delay(
        to=user.email,
        workspace_name=organization.name,
        confirmation_url=confirmation_url,
        year=datetime.now(UTC).year,
    )

    logger.info(
        "Workspace deletion requested | org_id=%s user_id=%s email=%s",
        organization.id,
        user.id,
        user.email,
    )

    return templates.TemplateResponse(
        request,
        "tenants/deletion_requested.html",
        {
            **(await _get_common_context(request, db, auth_result, "organization_settings")),
            "email": user.email,
            "workspace_name": organization.name,
            "expires_at": deletion_request.expires_at,
        },
    )


@router.get("/delete/confirm/{token}", response_class=HTMLResponse)
async def confirm_deletion_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show workspace deletion confirmation page (from email link)."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    ctx = await _get_common_context(request, db, auth_result, "organization_settings")

    result = await db.execute(
        select(WorkspaceDeletionRequest).where(WorkspaceDeletionRequest.token == token)
    )
    deletion_request = result.scalar_one_or_none()

    if not deletion_request:
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Deletion request not found",
                "error_detail": "This deletion link is invalid or has already been used.",
            },
        )

    # Check if expired
    if deletion_request.is_expired:
        if deletion_request.status == DeletionRequestStatus.PENDING:
            deletion_request.mark_expired()
            await db.commit()
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Deletion request expired",
                "error_detail": "This deletion link has expired. Please request a new deletion from the workspace settings.",
            },
        )

    # Check if already processed
    if deletion_request.status != DeletionRequestStatus.PENDING:
        status_messages = {
            DeletionRequestStatus.CONFIRMED: "This workspace has already been deleted.",
            DeletionRequestStatus.CANCELLED: "This deletion request was cancelled.",
            DeletionRequestStatus.EXPIRED: "This deletion link has expired.",
        }
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": f"Deletion request {deletion_request.status.value}",
                "error_detail": status_messages.get(
                    deletion_request.status,
                    "This deletion request is no longer valid.",
                ),
            },
        )

    # Get organization details
    org_result = await db.execute(
        select(Organization).where(Organization.id == deletion_request.organization_id)
    )
    organization: Organization | None = org_result.scalar_one_or_none()

    if not organization:
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Workspace not found",
                "error_detail": "The workspace associated with this deletion request no longer exists.",
            },
        )

    return templates.TemplateResponse(
        request,
        "tenants/deletion_confirm.html",
        {
            **ctx,
            "deletion_request": deletion_request,
            "organization": organization,
            "workspace_name": organization.name,
            "expires_at": deletion_request.expires_at,
        },
    )


@router.post("/delete/confirm/{token}", response_class=HTMLResponse)
async def execute_deletion(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Execute workspace deletion after email confirmation."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    ctx = await _get_common_context(request, db, auth_result, "organization_settings")

    result = await db.execute(
        select(WorkspaceDeletionRequest).where(WorkspaceDeletionRequest.token == token)
    )
    deletion_request = result.scalar_one_or_none()

    if not deletion_request:
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Deletion request not found",
                "error_detail": "This deletion link is invalid or has already been used.",
            },
        )

    # Check if valid (pending and not expired)
    if not deletion_request.is_valid:
        if deletion_request.is_expired and deletion_request.status == DeletionRequestStatus.PENDING:
            deletion_request.mark_expired()
            await db.commit()
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Deletion request invalid",
                "error_detail": "This deletion link is no longer valid. It may have expired or been cancelled.",
            },
        )

    # Get organization
    org_result = await db.execute(
        select(Organization).where(Organization.id == deletion_request.organization_id)
    )
    organization: Organization | None = org_result.scalar_one_or_none()

    if not organization:
        deletion_request.cancel()
        await db.commit()
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Workspace not found",
                "error_detail": "The workspace has already been deleted or no longer exists.",
            },
        )

    workspace_name = organization.name
    org_id = organization.id

    # Check if organization has an active paid subscription
    billing_client = get_billing_client()
    subscription = None
    if billing_client.is_configured:
        try:
            subscription = await billing_client.get_tenant_subscription(str(org_id))
        except Exception as e:
            logger.warning(f"Failed to get subscription for org {org_id}: {e}")

    # If there's an active subscription with a future period end, schedule deletion
    if (
        subscription
        and subscription.status in ("active", "trialing")
        and subscription.current_period_end
        and subscription.current_period_end > datetime.now(UTC)
    ):
        # Cancel the subscription at period end
        cancel_result = await billing_client.cancel_subscription(
            subscription_id=subscription.id,
            cancel_at_period_end=True,
        )

        if cancel_result.success:
            # Schedule deletion for end of billing period
            scheduled_date = subscription.current_period_end
            deletion_request.schedule(
                deletion_date=scheduled_date,
                subscription_cancelled=True,
            )
            await db.commit()

            # Send scheduled deletion email
            send_workspace_deletion_scheduled_email.delay(
                to=deletion_request.email,
                workspace_name=workspace_name,
                deletion_date=scheduled_date.strftime("%B %d, %Y at %H:%M UTC"),
                year=datetime.now(UTC).year,
            )

            logger.info(
                "Workspace deletion scheduled | org_id=%s org_name=%s user_id=%s scheduled_at=%s",
                org_id,
                workspace_name,
                deletion_request.requested_by,
                scheduled_date.isoformat(),
            )

            return templates.TemplateResponse(
                request,
                "tenants/deletion_scheduled.html",
                {
                    **ctx,
                    "workspace_name": workspace_name,
                    "scheduled_deletion_at": scheduled_date,
                    "subscription_cancelled": True,
                },
            )
        else:
            # Cancellation failed, log but continue with immediate deletion
            logger.error(
                "Failed to cancel subscription for org %s: %s",
                org_id,
                cancel_result.error,
            )

    # No active paid subscription or cancellation failed - delete immediately
    deletion_request.confirm()
    user_email = deletion_request.email

    # Delete the organization (cascade will handle collections, documents, members, invitations)
    await db.delete(organization)
    await db.commit()

    # Send deletion confirmation email
    settings = get_settings()
    support_url = settings.support_url
    send_workspace_deleted_email.delay(
        to=user_email,
        workspace_name=workspace_name,
        support_url=support_url,
        year=datetime.now(UTC).year,
    )

    logger.info(
        "Workspace deleted via email confirmation | org_id=%s org_name=%s user_id=%s",
        org_id,
        workspace_name,
        deletion_request.requested_by,
    )

    # Check if user has remaining workspaces
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == deletion_request.requested_by)
        .limit(1)
    )
    has_remaining_workspaces = result.scalar_one_or_none() is not None

    if has_remaining_workspaces:
        # User still has workspaces, redirect to dashboard
        response = RedirectResponse(url="/dashboard?deleted=true", status_code=302)
        response.delete_cookie(
            ACTIVE_TENANT_COOKIE,
            path="/",
            samesite="lax",
        )
        return response
    else:
        # No remaining workspaces, log the user out
        return RedirectResponse(url="/auth/logout?redirect=/", status_code=302)


@router.get("/delete/cancel/{cancel_token}", response_class=HTMLResponse)
async def cancel_scheduled_deletion(
    request: Request,
    cancel_token: str,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Cancel a scheduled workspace deletion and reactivate subscription."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    ctx = await _get_common_context(request, db, auth_result, "organization_settings")

    result = await db.execute(
        select(WorkspaceDeletionRequest).where(
            WorkspaceDeletionRequest.cancel_token == cancel_token
        )
    )
    deletion_request = result.scalar_one_or_none()

    if not deletion_request:
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Cancellation link not found",
                "error_detail": "This cancellation link is invalid or has already been used.",
            },
        )

    # Check if still scheduled
    if deletion_request.status != DeletionRequestStatus.SCHEDULED:
        status_messages = {
            DeletionRequestStatus.CONFIRMED: "This workspace has already been deleted.",
            DeletionRequestStatus.CANCELLED: "This deletion has already been cancelled.",
            DeletionRequestStatus.PENDING: "This deletion request is still pending confirmation.",
            DeletionRequestStatus.EXPIRED: "This deletion request has expired.",
        }
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": f"Cannot cancel - status: {deletion_request.status.value}",
                "error_detail": status_messages.get(
                    deletion_request.status,
                    "This deletion request is no longer valid.",
                ),
            },
        )

    # Get organization
    org_result = await db.execute(
        select(Organization).where(Organization.id == deletion_request.organization_id)
    )
    organization: Organization | None = org_result.scalar_one_or_none()

    if not organization:
        deletion_request.cancel()
        await db.commit()
        return templates.TemplateResponse(
            request,
            "tenants/deletion_error.html",
            {
                **ctx,
                "error": "Workspace not found",
                "error_detail": "The workspace has already been deleted.",
            },
        )

    workspace_name = organization.name
    org_id = organization.id

    # Try to reactivate the subscription if it was cancelled
    reactivation_success = False
    if deletion_request.subscription_cancelled:
        billing_client = get_billing_client()
        if billing_client.is_configured:
            try:
                subscription = await billing_client.get_tenant_subscription(str(org_id))
                if subscription and subscription.cancel_at_period_end:
                    reactivate_result = await billing_client.reactivate_subscription(
                        subscription_id=subscription.id,
                    )
                    reactivation_success = reactivate_result.success
                    if not reactivation_success:
                        logger.error(
                            "Failed to reactivate subscription for org %s: %s",
                            org_id,
                            reactivate_result.error,
                        )
            except Exception as e:
                logger.error(f"Failed to reactivate subscription for org {org_id}: {e}")

    # Cancel the deletion request
    deletion_request.cancel()
    await db.commit()

    logger.info(
        "Scheduled workspace deletion cancelled | org_id=%s org_name=%s subscription_reactivated=%s",
        org_id,
        workspace_name,
        reactivation_success,
    )

    return templates.TemplateResponse(
        request,
        "tenants/deletion_cancelled.html",
        {
            **ctx,
            "workspace_name": workspace_name,
            "subscription_reactivated": reactivation_success,
        },
    )


@router.get("/members", response_class=HTMLResponse)
async def organization_members(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Organization members page."""
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

    # Get members
    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization.id)
        .order_by(OrganizationMember.created_at)
    )
    members = result.scalars().all()

    # Get pending invitations
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.status == InvitationStatus.PENDING,
            OrganizationInvitation.expires_at > datetime.now(UTC),
        )
    )
    invitations = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "tenants/members.html",  # Keep template path for now
        {
            **(await _get_common_context(request, db, auth_result, "organization_members")),
            "members": members,
            "invitations": invitations,
        },
    )


@router.get("/invite", response_class=HTMLResponse)
async def invite_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Show invitation form."""
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

    return templates.TemplateResponse(
        request,
        "tenants/invite.html",  # Keep template path for now
        {
            **(await _get_common_context(request, db, auth_result, "organization_members")),
        },
    )


@router.post("/invite", response_class=HTMLResponse)
async def create_invitation(
    request: Request,
    email: str = Form(...),
    role: str = Form("member"),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Create a new invitation."""
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
    user = auth_result.user

    # Validate role
    try:
        member_role = OrganizationMemberRole(role)
        # Only owners can invite other owners
        if member_role == OrganizationMemberRole.OWNER and not auth_result.is_tenant_owner:
            member_role = OrganizationMemberRole.ADMIN
    except ValueError:
        member_role = OrganizationMemberRole.MEMBER

    # Check if email already has a pending invitation
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.email == email.lower(),
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return templates.TemplateResponse(
            request,
            "tenants/invite.html",  # Keep template path for now
            {
                **(await _get_common_context(request, db, auth_result, "organization_members")),
                "error": f"An invitation for {email} is already pending.",
                "form_email": email,
                "form_role": role,
            },
        )

    # Create invitation
    invitation = OrganizationInvitation(
        organization_id=organization.id,
        email=email.lower(),
        role=member_role,
        token=secrets.token_urlsafe(32),
        invited_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invitation)
    await db.commit()

    # Send invitation email
    from knowledge.tasks import send_workspace_invitation_email

    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")
    invitation_url = f"{base_url}/tenants/invites/{invitation.token}"
    inviter_name = user.display_name or user.email or "A team member"

    send_workspace_invitation_email.delay(
        to=email.lower(),
        workspace_name=organization.name,
        inviter_name=inviter_name,
        role=member_role.value,
        invitation_url=invitation_url,
        year=datetime.now(UTC).year,
    )

    return RedirectResponse(url="/organizations/members", status_code=302)


@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(
    request: Request,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Resend an invitation email."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant
    user = auth_result.user

    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.status == InvitationStatus.PENDING,
            OrganizationInvitation.expires_at > datetime.now(UTC),
        )
    )
    invitation = result.scalar_one_or_none()

    if invitation:
        from knowledge.tasks import send_workspace_invitation_email

        settings = get_settings()
        base_url = settings.app_base_url.rstrip("/")
        invitation_url = f"{base_url}/tenants/invites/{invitation.token}"
        inviter_name = user.display_name or user.email or "A team member"

        send_workspace_invitation_email.delay(
            to=invitation.email,
            workspace_name=organization.name,
            inviter_name=inviter_name,
            role=invitation.role.value,
            invitation_url=invitation_url,
            year=datetime.now(UTC).year,
        )

    return RedirectResponse(url="/organizations/members", status_code=302)


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    request: Request,
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Revoke a pending invitation."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant

    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.status == InvitationStatus.PENDING,
        )
    )
    invitation = result.scalar_one_or_none()

    if invitation:
        invitation.status = InvitationStatus.REVOKED
        await db.commit()

    return RedirectResponse(url="/organizations/members", status_code=302)


@router.post("/members/{member_id}/remove")
async def remove_member(
    request: Request,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Remove a member from the organization."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant
    user = auth_result.user

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization.id,
        )
    )
    member = result.scalar_one_or_none()

    if member:
        # Can't remove yourself
        if member.user_id == user.id:
            return RedirectResponse(url="/organizations/members", status_code=302)

        # Can't remove owner unless you're owner
        if member.role == OrganizationMemberRole.OWNER and not auth_result.is_tenant_owner:
            return RedirectResponse(url="/organizations/members", status_code=302)

        await db.delete(member)
        await db.commit()

    return RedirectResponse(url="/organizations/members", status_code=302)


@router.post("/members/{member_id}/role")
async def update_member_role(
    request: Request,
    member_id: UUID,
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Update a member's role."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant
    user = auth_result.user

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization.id,
        )
    )
    member = result.scalar_one_or_none()

    if member:
        # Can't change your own role
        if member.user_id == user.id:
            return RedirectResponse(url="/organizations/members", status_code=302)

        try:
            new_role = OrganizationMemberRole(role)
            # Only owners can promote to owner
            if new_role == OrganizationMemberRole.OWNER and not auth_result.is_tenant_owner:
                new_role = OrganizationMemberRole.ADMIN
            member.role = new_role
            await db.commit()
        except ValueError:
            pass

    return RedirectResponse(url="/organizations/members", status_code=302)


# =============================================================================
# Public invitation routes (no auth required to view)
# =============================================================================


@router.get("/invites/{token}", response_class=HTMLResponse)
async def view_invitation(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """View an invitation (public page)."""
    result = await db.execute(
        select(OrganizationInvitation).where(OrganizationInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        return templates.TemplateResponse(
            request,
            "tenants/invite_error.html",  # Keep template path for now
            {
                "user": None,
                "error": "Invitation not found",
            },
        )

    if invitation.status != InvitationStatus.PENDING:
        return templates.TemplateResponse(
            request,
            "tenants/invite_error.html",  # Keep template path for now
            {
                "user": None,
                "error": f"This invitation has been {invitation.status.value}",
            },
        )

    if invitation.expires_at < datetime.now(UTC):
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        return templates.TemplateResponse(
            request,
            "tenants/invite_error.html",  # Keep template path for now
            {
                "user": None,
                "error": "This invitation has expired",
            },
        )

    # Get organization
    result = await db.execute(
        select(Organization).where(Organization.id == invitation.organization_id)
    )
    organization = result.scalar_one_or_none()

    # Check if user is logged in
    access_token = await get_token_from_cookie(request)
    user = None

    if access_token:
        from knowledge.auth.jwt import get_jwt_validator
        from knowledge.auth.models import User

        try:
            jwt_validator = get_jwt_validator()
            claims = await jwt_validator.validate_token_with_introspection(access_token)
            user = User.from_jwt_claims(claims)
        except Exception:
            pass

    return templates.TemplateResponse(
        request,
        "tenants/invite_view.html",  # Keep template path for now
        {
            "user": user,
            "invitation": invitation,
            "tenant": organization,  # Backward compat
            "organization": organization,
        },
    )


@router.post("/invites/{token}/accept")
async def accept_invitation(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Accept an invitation."""
    # Must be logged in
    access_token = await get_token_from_cookie(request)
    if not access_token:
        return RedirectResponse(
            url=f"/auth/login?redirect=/organizations/invites/{token}",
            status_code=302,
        )

    from knowledge.auth.jwt import get_jwt_validator
    from knowledge.auth.models import User

    try:
        jwt_validator = get_jwt_validator()
        claims = await jwt_validator.validate_token_with_introspection(access_token)
        user = User.from_jwt_claims(claims)
    except Exception:
        return RedirectResponse(
            url=f"/auth/login?redirect=/organizations/invites/{token}",
            status_code=302,
        )

    # Get invitation
    result = await db.execute(
        select(OrganizationInvitation).where(OrganizationInvitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation or invitation.status != InvitationStatus.PENDING:
        return RedirectResponse(url=f"/organizations/invites/{token}", status_code=302)

    if invitation.expires_at < datetime.now(UTC):
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        return RedirectResponse(url=f"/organizations/invites/{token}", status_code=302)

    # Check if already a member
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == invitation.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Already a member, just mark invitation as accepted
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(UTC)
        await db.commit()
    else:
        # Create membership
        member = OrganizationMember(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
        )
        db.add(member)

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.now(UTC)
        await db.commit()

    # Set active tenant cookie and redirect to dashboard
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=ACTIVE_TENANT_COOKIE,  # Keep cookie name for backward compat
        value=str(invitation.organization_id),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


# =============================================================================
# Custom Domain routes (Enterprise plan only)
# =============================================================================


def _domain_page_context(settings, **extra):
    """Context shared by the renderings of the custom domain page."""
    return {"cname_target": settings.custom_domain_cname_target, "settings": settings, **extra}


async def _render_domain_page(request, db, auth_result, settings, error=None):
    return templates.TemplateResponse(
        request,
        "tenants/domain.html",
        {
            **(await _get_common_context(request, db, auth_result, "organization_settings")),
            **_domain_page_context(settings, error=error),
        },
    )


def _registration_message(error: CustomDomainError) -> str:
    """Explain to the customer why the service did not take the request."""
    if error.status_code == 409:
        return "This domain is already registered."
    if error.status_code in (400, 403):
        return error.detail
    return "The custom domain service is not available right now. Please try again later."


@router.get("/domain", response_class=HTMLResponse)
async def custom_domain_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Custom domain settings page (Enterprise only)."""
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

    # Check Enterprise plan
    if not organization.can_use_custom_domain:
        return RedirectResponse(url="/organizations/settings", status_code=302)

    return await _render_domain_page(request, db, auth_result, get_settings())


@router.post("/domain", response_class=HTMLResponse)
async def update_custom_domain(
    request: Request,
    domain: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Register the custom domain of the organization in the custom-domain service."""
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
    settings = get_settings()

    if not organization.can_use_custom_domain:
        return RedirectResponse(url="/organizations/settings", status_code=302)

    domain = domain.lower().strip()

    # Validate domain format
    valid, error = domain_service.validate_domain(domain)
    if not valid:
        return await _render_domain_page(request, db, auth_result, settings, error)

    # Check if domain is already in use by another organization
    result = await db.execute(
        select(Organization).where(
            Organization.custom_domain == domain,
            Organization.id != organization.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return await _render_domain_page(
            request,
            db,
            auth_result,
            settings,
            "This domain is already in use by another organization.",
        )

    # The previous domain of the workspace is replaced: the service forgets it first
    previous_id = organization.custom_domain_service_id
    client = get_custom_domain_client()
    try:
        if previous_id:
            await client.delete(previous_id)
        registered = await client.register(domain, str(organization.id))
    except CustomDomainError as e:
        logger.error("Custom domain registration failed for %s: %s", domain, e.detail)
        return await _render_domain_page(
            request, db, auth_result, settings, _registration_message(e)
        )

    organization.custom_domain = domain
    organization.custom_domain_service_id = registered.id
    organization.custom_domain_cname_target = registered.cname_target or None
    organization.custom_domain_status = CustomDomainStatus.PENDING
    organization.custom_domain_error = None
    organization.custom_domain_verified_at = None
    organization.custom_domain_ssl_at = None
    organization.custom_domain_checked_at = None
    await db.commit()

    return RedirectResponse(url="/organizations/domain", status_code=302)


@router.post("/domain/verify", response_class=HTMLResponse)
async def retry_domain_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Ask the custom-domain service to verify the DNS of the domain again."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant

    if organization.custom_domain:
        client = get_custom_domain_client()
        try:
            if organization.custom_domain_service_id:
                status = await client.verify(organization.custom_domain_service_id)
                domain_service.apply_status(organization, status)
            else:
                # Never registered (legacy domain) or lost by the service: register it
                registered = await client.register(organization.custom_domain, str(organization.id))
                organization.custom_domain_service_id = registered.id
                organization.custom_domain_cname_target = registered.cname_target or None
                domain_service.apply_status(organization, registered.status)
            await db.commit()
        except CustomDomainError as e:
            logger.error("Custom domain verification failed: %s", e.detail)
            return await _render_domain_page(
                request, db, auth_result, get_settings(), _registration_message(e)
            )

    return RedirectResponse(url="/organizations/domain", status_code=302)


@router.get("/domain/status")
async def domain_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Get custom domain status (JSON endpoint for polling)."""
    if isinstance(auth_result, RedirectResponse):
        return {"error": "Not authenticated"}

    if not auth_result.tenant:
        return {"error": "No organization selected"}

    organization = auth_result.tenant

    if not organization.custom_domain:
        return {"has_domain": False}

    return {
        "has_domain": True,
        "domain": organization.custom_domain,
        "status": organization.custom_domain_status.value
        if organization.custom_domain_status
        else None,
        "error": organization.custom_domain_error,
    }


@router.post("/domain/remove", response_class=HTMLResponse)
async def remove_custom_domain(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
):
    """Remove the custom domain of the organization, here and in the service."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    if not auth_result.tenant or not auth_result.is_tenant_admin:
        return RedirectResponse(url="/dashboard", status_code=302)

    organization = auth_result.tenant

    # The service removes the certificate and the web server configuration; the domain
    # stays on the workspace until the service has accepted the removal.
    if organization.custom_domain_service_id:
        try:
            await get_custom_domain_client().delete(organization.custom_domain_service_id)
        except CustomDomainError as e:
            logger.error("Custom domain removal failed: %s", e.detail)
            return await _render_domain_page(
                request, db, auth_result, get_settings(), _registration_message(e)
            )

    domain_service.clear_domain(organization)
    await db.commit()

    return RedirectResponse(url="/organizations/domain", status_code=302)
