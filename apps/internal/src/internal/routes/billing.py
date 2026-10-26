# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Billing admin routes for HTML pages.

Provides admin views for the Multi-SaaS Stripe Billing Platform.

Scopes required:
- billing:read - View billing data
- billing:write - Create/update billing resources
- billing:admin - Full administrative access
"""

import json
from typing import Any
from urllib.parse import quote_plus, urlsplit

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import require_resource_scopes_or_redirect
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services.billing_client import billing_client

router = APIRouter(prefix="/billing", tags=["billing"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Scope dependencies
# Use require_resource_scopes_or_redirect for all to ensure sidebar scopes are fetched
require_billing_read = require_resource_scopes_or_redirect(
    "billing", extra_scopes=["billing:admin"]
)
require_billing_write = require_resource_scopes_or_redirect(
    "billing", required_scope="billing:write", extra_scopes=["billing:admin"]
)
# The admin scope is not one of the resource scopes: it must be requested to be granted
require_billing_admin = require_resource_scopes_or_redirect(
    "billing", required_scope="billing:admin", extra_scopes=["billing:admin"]
)


def parse_checkout_urls(text: str) -> list[str] | None:
    """Read the checkout URL allow-list of a form: one URL prefix per line.

    The billing service stays the authority on what it accepts; this only catches the usual
    mistakes (no scheme, credentials, query string, fragment) before the round trip.

    Raises:
        ValueError: If a line is not an acceptable URL prefix.

    Returns:
        The prefixes without duplicates, or None when the text has none (the list is cleared).
    """
    urls: list[str] = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry:
            continue
        parts = urlsplit(entry)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"'{entry}' is not an absolute http(s) URL")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError(f"'{entry}' must not contain credentials, a query or a fragment")
        if entry not in urls:
            urls.append(entry)
    return urls or None


def parse_branding(text: str) -> dict | None:
    """Read the branding of a form: a JSON object, or nothing (the branding is cleared).

    Raises:
        ValueError: If the text is not a JSON object.
    """
    if not text.strip():
        return None
    try:
        branding = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Branding is not valid JSON: {error.msg}") from error
    if not isinstance(branding, dict):
        raise ValueError("Branding must be a JSON object")
    return branding


def _error_redirect(url: str, message: str) -> RedirectResponse:
    """Redirect to ``url`` with an ``error`` banner."""
    return RedirectResponse(url=f"{url}?error={quote_plus(message)}", status_code=303)


# =============================================================================
# Dashboard
# =============================================================================


@router.get("", response_class=HTMLResponse)
async def billing_dashboard(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """Billing dashboard - overview of all SaaS apps."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Billing dashboard accessed | user_id=%s client_id=%s",
        user.id,
        settings.oauth2_client_id,
    )

    # Fetch all SaaS apps
    saas_apps = await billing_client.list_saas_apps(include_inactive=True)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/dashboard.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_apps": saas_apps,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


# =============================================================================
# SaaS Apps
# =============================================================================


@router.get("/saas/new", response_class=HTMLResponse)
async def saas_app_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """New SaaS app form."""
    if not isinstance(auth_result, User):
        return auth_result

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/saas_form.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": auth_result,
            "saas_app": None,
            "is_edit": False,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/new")
async def saas_app_create(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(None),
    webhook_url: str = Form(None),
    webhook_secret: str = Form(None),
    checkout_urls: str = Form(""),
    branding_json: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Create a new SaaS app."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        allowlist = parse_checkout_urls(checkout_urls)
        branding = parse_branding(branding_json)
    except ValueError as error:
        return _error_redirect("/billing/saas/new", str(error))

    saas_app = await billing_client.create_saas_app(
        name=name,
        slug=slug,
        description=description or None,
        webhook_url=webhook_url or None,
        webhook_secret=webhook_secret or None,
        branding=branding,
        checkout_url_allowlist=allowlist,
    )

    if saas_app:
        logger.info(
            "SaaS app created | user_id=%s saas_id=%s name=%s",
            user.id,
            saas_app.id,
            saas_app.name,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_app.id}?success=SaaS+app+created+successfully",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url="/billing/saas/new?error=Failed+to+create+SaaS+app",
            status_code=303,
        )


@router.get("/saas/{saas_id}", response_class=HTMLResponse)
async def saas_app_detail(
    request: Request,
    saas_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """SaaS app detail view with products and customers."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Fetch SaaS app details
    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    # Fetch related data
    products = await billing_client.list_products(saas_id, include_inactive=True)
    customers = await billing_client.list_customers(saas_id, limit=settings.billing_recent_limit)
    subscriptions = await billing_client.list_subscriptions(
        saas_id, limit=settings.billing_recent_limit
    )
    # The OAuth clients bound to the app are only shown to administrators
    bindings = (
        await billing_client.list_saas_clients(saas_id) if user.has_scope("billing:admin") else []
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/saas_detail.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "products": products,
            "customers": customers,
            "subscriptions": subscriptions,
            "bindings": bindings,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/clients")
async def saas_client_bind(
    request: Request,
    saas_id: str,
    client_id: str = Form(...),
    auth_result: User | RedirectResponse = Depends(require_billing_admin),
):
    """Bind an OAuth client to a SaaS app: it may then act on that app's data."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    client_id = client_id.strip()
    if not client_id or any(character.isspace() for character in client_id):
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}?error=A+client+id+has+no+spaces+and+is+not+empty",
            status_code=303,
        )

    binding = await billing_client.bind_client(saas_id, client_id)

    if binding:
        logger.info(
            "Client bound | user_id=%s saas_id=%s bound_client_id=%s",
            user.id,
            saas_id,
            client_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}?success=Client+bound",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/billing/saas/{saas_id}?error=Failed+to+bind+client",
        status_code=303,
    )


@router.post("/saas/{saas_id}/clients/unbind")
async def saas_client_unbind(
    request: Request,
    saas_id: str,
    client_id: str = Form(...),
    auth_result: User | RedirectResponse = Depends(require_billing_admin),
):
    """Remove the binding of an OAuth client to a SaaS app."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    if await billing_client.unbind_client(saas_id, client_id.strip()):
        logger.info(
            "Client unbound | user_id=%s saas_id=%s unbound_client_id=%s",
            user.id,
            saas_id,
            client_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}?success=Client+unbound",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/billing/saas/{saas_id}?error=Failed+to+unbind+client",
        status_code=303,
    )


@router.get("/saas/{saas_id}/edit", response_class=HTMLResponse)
async def saas_app_edit(
    request: Request,
    saas_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Edit SaaS app form."""
    if not isinstance(auth_result, User):
        return auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/saas_form.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": auth_result,
            "saas_app": saas_app,
            "is_edit": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/edit")
async def saas_app_update(
    request: Request,
    saas_id: str,
    name: str = Form(...),
    description: str = Form(None),
    webhook_url: str = Form(None),
    webhook_secret: str = Form(None),
    checkout_urls: str = Form(""),
    branding_json: str = Form(""),
    is_active: bool = Form(False),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Update a SaaS app (an unchecked "Active" box is not submitted: it deactivates).

    The form always carries the checkout URL allow-list and the branding: empty fields clear them.
    """
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    try:
        allowlist = parse_checkout_urls(checkout_urls)
        branding = parse_branding(branding_json)
    except ValueError as error:
        return _error_redirect(f"/billing/saas/{saas_id}/edit", str(error))

    saas_app = await billing_client.update_saas_app(
        saas_id=saas_id,
        name=name,
        description=description or None,
        webhook_url=webhook_url or None,
        webhook_secret=webhook_secret or None,
        is_active=is_active,
        branding=branding,
        checkout_url_allowlist=allowlist,
    )

    if saas_app:
        logger.info(
            "SaaS app updated | user_id=%s saas_id=%s",
            user.id,
            saas_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}?success=SaaS+app+updated+successfully",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/edit?error=Failed+to+update+SaaS+app",
            status_code=303,
        )


# =============================================================================
# Products
# =============================================================================


@router.get("/saas/{saas_id}/products", response_class=HTMLResponse)
async def products_list(
    request: Request,
    saas_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """List all products for a SaaS app."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    products = await billing_client.list_products(saas_id, include_inactive=True)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/products_list.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "products": products,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/saas/{saas_id}/products/new", response_class=HTMLResponse)
async def product_new(
    request: Request,
    saas_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """New product form."""
    if not isinstance(auth_result, User):
        return auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/product_form.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": auth_result,
            "saas_app": saas_app,
            "product": None,
            "is_edit": False,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/products/new")
async def product_create(
    request: Request,
    saas_id: str,
    name: str = Form(...),
    description: str = Form(None),
    slug: str = Form(None),
    sort_order: int = Form(0),
    default_trial_days: int = Form(0),
    is_recommended: bool = Form(False),
    features_json: str = Form("[]"),
    limits_json: str = Form("{}"),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Create a new product in Stripe with features, limits, and trial settings."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Parse features and limits from JSON
    try:
        features = json.loads(features_json) if features_json else []
        limits = json.loads(limits_json) if limits_json else {}
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in product create: %s", e)
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/new?error=Invalid+JSON+format",
            status_code=303,
        )

    # Build metadata dict
    metadata: dict[str, Any] = {
        "slug": slug or "",
        "sort_order": sort_order,
        "default_trial_days": default_trial_days if default_trial_days > 0 else None,
        "is_recommended": is_recommended,
        "features": features,
        "limits": limits,
    }

    product = await billing_client.create_product(
        saas_id=saas_id,
        name=name,
        description=description or None,
        metadata=metadata,
    )

    if product:
        logger.info(
            "Product created | user_id=%s saas_id=%s product_id=%s stripe_id=%s",
            user.id,
            saas_id,
            product.id,
            product.stripe_product_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product.id}?success=Product+created+in+Stripe",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/new?error=Failed+to+create+product",
            status_code=303,
        )


@router.get("/saas/{saas_id}/products/{product_id}", response_class=HTMLResponse)
async def product_detail(
    request: Request,
    saas_id: str,
    product_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """Product detail with prices."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    product = await billing_client.get_product(saas_id, product_id)
    if not product:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products?error=Product+not+found",
            status_code=303,
        )

    prices = await billing_client.list_prices(saas_id, product_id, include_inactive=True)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/product_detail.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "product": product,
            "prices": prices,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/saas/{saas_id}/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit(
    request: Request,
    saas_id: str,
    product_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Edit product form with features and limits."""
    if not isinstance(auth_result, User):
        return auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    product = await billing_client.get_product(saas_id, product_id)
    if not product:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products?error=Product+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/product_form.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": auth_result,
            "saas_app": saas_app,
            "product": product,
            "is_edit": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/products/{product_id}/edit")
async def product_update(
    request: Request,
    saas_id: str,
    product_id: str,
    name: str = Form(...),
    description: str = Form(None),
    slug: str = Form(None),
    sort_order: int = Form(0),
    default_trial_days: int = Form(0),
    is_recommended: bool = Form(False),
    is_active: bool = Form(False),
    features_json: str = Form("[]"),
    limits_json: str = Form("{}"),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Update a product with features, limits, and trial settings."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Parse features and limits from JSON
    try:
        features = json.loads(features_json) if features_json else []
        limits = json.loads(limits_json) if limits_json else {}
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in product update: %s", e)
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}/edit?error=Invalid+JSON+format",
            status_code=303,
        )

    # Build metadata dict
    metadata: dict[str, Any] = {
        "slug": slug or "",
        "sort_order": sort_order,
        "default_trial_days": default_trial_days if default_trial_days > 0 else None,
        "is_recommended": is_recommended,
        "features": features,
        "limits": limits,
    }

    product = await billing_client.update_product(
        saas_id=saas_id,
        product_id=product_id,
        name=name,
        description=description or None,
        metadata=metadata,
        is_active=is_active,
    )

    if product:
        logger.info(
            "Product updated | user_id=%s saas_id=%s product_id=%s",
            user.id,
            saas_id,
            product_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}?success=Product+updated+successfully",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}/edit?error=Failed+to+update+product",
            status_code=303,
        )


# =============================================================================
# Prices
# =============================================================================


@router.get("/saas/{saas_id}/products/{product_id}/prices/new", response_class=HTMLResponse)
async def price_new(
    request: Request,
    saas_id: str,
    product_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """New price form."""
    if not isinstance(auth_result, User):
        return auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    product = await billing_client.get_product(saas_id, product_id)

    if not saas_app or not product:
        return RedirectResponse(
            url="/billing?error=Resource+not+found",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/price_form.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": auth_result,
            "saas_app": saas_app,
            "product": product,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/products/{product_id}/prices/new")
async def price_create(
    request: Request,
    saas_id: str,
    product_id: str,
    unit_amount: int = Form(...),
    currency: str = Form(""),
    billing_type: str = Form("recurring"),
    recurring_interval: str = Form(""),
    usage_type: str = Form("licensed"),
    nickname: str = Form(None),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Create a new price in Stripe."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    price = await billing_client.create_price(
        saas_id=saas_id,
        product_id=product_id,
        unit_amount=unit_amount,
        currency=currency.strip().lower() or None,
        billing_type=billing_type,
        recurring_interval=(recurring_interval or None if billing_type == "recurring" else None),
        usage_type=usage_type,
        nickname=nickname or None,
    )

    if price:
        logger.info(
            "Price created | user_id=%s saas_id=%s product_id=%s stripe_id=%s",
            user.id,
            saas_id,
            product_id,
            price.stripe_price_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}?success=Price+created+in+Stripe",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}/prices/new?error=Failed+to+create+price",
            status_code=303,
        )


@router.post("/saas/{saas_id}/products/{product_id}/prices/{price_id}/toggle")
async def price_toggle(
    request: Request,
    saas_id: str,
    product_id: str,
    price_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Toggle a price active/inactive status."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Get current price to determine new state
    prices = await billing_client.list_prices(saas_id, product_id, include_inactive=True)
    current_price = next((p for p in prices if p.id == price_id), None)

    if not current_price:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}?error=Price+not+found",
            status_code=303,
        )

    new_state = not current_price.is_active
    price = await billing_client.update_price(
        saas_id=saas_id,
        product_id=product_id,
        price_id=price_id,
        is_active=new_state,
    )

    if price:
        action = "activated" if new_state else "deactivated"
        logger.info(
            "Price %s | user_id=%s saas_id=%s price_id=%s",
            action,
            user.id,
            saas_id,
            price_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}?success=Price+{action}",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/products/{product_id}?error=Failed+to+update+price",
            status_code=303,
        )


# =============================================================================
# Customers
# =============================================================================


@router.get("/saas/{saas_id}/customers", response_class=HTMLResponse)
async def customers_list(
    request: Request,
    saas_id: str,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """List customers for a SaaS app."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = settings.billing_page_size
    offset = (page - 1) * per_page

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    customers = await billing_client.list_customers(saas_id, limit=per_page, offset=offset)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/customers_list.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "customers": customers,
            "per_page": per_page,
            "page": page,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/saas/{saas_id}/customers/{customer_id}", response_class=HTMLResponse)
async def customer_detail(
    request: Request,
    saas_id: str,
    customer_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """Customer detail with subscriptions."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    customer = await billing_client.get_customer(saas_id, customer_id)
    if not customer:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/customers?error=Customer+not+found",
            status_code=303,
        )

    customer_subscriptions = await billing_client.list_customer_subscriptions(saas_id, customer_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/customer_detail.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "customer": customer,
            "subscriptions": customer_subscriptions,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/customers/{customer_id}/portal")
async def customer_portal_redirect(
    request: Request,
    saas_id: str,
    customer_id: str,
    return_url: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """Redirect to Stripe Customer Portal.

    The operator comes back to ``return_url`` or, by default, to the first entry of the
    checkout URL allow-list of the SaaS app (the billing service refuses any other URL).
    """
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    # Stripe sends the operator back to a URL the SaaS app accepts: its checkout URL allow-list
    saas_app = await billing_client.get_saas_app(saas_id)
    allowed = (saas_app.checkout_url_allowlist or []) if saas_app else []
    return_url = return_url.strip() or (allowed[0] if allowed else "")
    if not return_url:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/customers/{customer_id}"
            "?error=No+return+URL%3A+add+one+to+the+checkout+URL+allow-list",
            status_code=303,
        )
    portal = await billing_client.get_customer_portal(saas_id, customer_id, return_url)

    if portal:
        logger.info(
            "Customer portal accessed | user_id=%s saas_id=%s customer_id=%s",
            user.id,
            saas_id,
            customer_id,
        )
        return RedirectResponse(url=portal.url, status_code=303)
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/customers/{customer_id}?error=Failed+to+create+portal+session",
            status_code=303,
        )


# =============================================================================
# Subscriptions
# =============================================================================


@router.get("/saas/{saas_id}/subscriptions", response_class=HTMLResponse)
async def subscriptions_list(
    request: Request,
    saas_id: str,
    status: str = Query(None),
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """List subscriptions for a SaaS app."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = settings.billing_page_size
    offset = (page - 1) * per_page

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    subscriptions = await billing_client.list_subscriptions(
        saas_id,
        status=status,
        limit=per_page,
        offset=offset,
    )

    statuses = [
        "active",
        "trialing",
        "past_due",
        "unpaid",
        "paused",
        "incomplete",
        "incomplete_expired",
        "canceled",
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/subscriptions_list.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "subscriptions": subscriptions,
            "per_page": per_page,
            "statuses": statuses,
            "status_filter": status,
            "page": page,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/saas/{saas_id}/subscriptions/{subscription_id}", response_class=HTMLResponse)
async def subscription_detail(
    request: Request,
    saas_id: str,
    subscription_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_read),
):
    """Subscription detail view."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    saas_app = await billing_client.get_saas_app(saas_id)
    if not saas_app:
        return RedirectResponse(
            url="/billing?error=SaaS+app+not+found",
            status_code=303,
        )

    subscription = await billing_client.get_subscription(saas_id, subscription_id)
    if not subscription:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions?error=Subscription+not+found",
            status_code=303,
        )

    # Fetch customer details
    customer = await billing_client.get_customer(saas_id, subscription.customer_id)

    return templates.TemplateResponse(
        request=request,
        name="admin/billing/subscription_detail.html",
        context={
            "request": request,
            "active_section": "billing",
            "user": user,
            "saas_app": saas_app,
            "subscription": subscription,
            "customer": customer,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/saas/{saas_id}/subscriptions/{subscription_id}/cancel")
async def subscription_cancel(
    request: Request,
    saas_id: str,
    subscription_id: str,
    cancel_immediately: bool = Form(False),
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Cancel a subscription."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    subscription = await billing_client.cancel_subscription(
        saas_id=saas_id,
        subscription_id=subscription_id,
        cancel_at_period_end=not cancel_immediately,
    )

    if subscription:
        action = "canceled" if cancel_immediately else "scheduled+for+cancellation"
        logger.info(
            "Subscription %s | user_id=%s saas_id=%s subscription_id=%s",
            action,
            user.id,
            saas_id,
            subscription_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}?success=Subscription+{action}",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}?error=Failed+to+cancel+subscription",
            status_code=303,
        )


@router.post("/saas/{saas_id}/subscriptions/{subscription_id}/reactivate")
async def subscription_reactivate(
    request: Request,
    saas_id: str,
    subscription_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Undo a cancellation scheduled for the end of the period."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    subscription = await billing_client.reactivate_subscription(
        saas_id=saas_id,
        subscription_id=subscription_id,
    )

    if subscription:
        logger.info(
            "Subscription reactivated | user_id=%s saas_id=%s subscription_id=%s",
            user.id,
            saas_id,
            subscription_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}"
            "?success=Subscription+reactivated",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}"
            "?error=Failed+to+reactivate+subscription",
            status_code=303,
        )


@router.post("/saas/{saas_id}/subscriptions/{subscription_id}/sync")
async def subscription_sync(
    request: Request,
    saas_id: str,
    subscription_id: str,
    auth_result: User | RedirectResponse = Depends(require_billing_write),
):
    """Sync a subscription from Stripe."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    subscription = await billing_client.sync_subscription(
        saas_id=saas_id,
        subscription_id=subscription_id,
    )

    if subscription:
        logger.info(
            "Subscription synced | user_id=%s saas_id=%s subscription_id=%s",
            user.id,
            saas_id,
            subscription_id,
        )
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}?success=Subscription+synced+from+Stripe",
            status_code=303,
        )
    else:
        return RedirectResponse(
            url=f"/billing/saas/{saas_id}/subscriptions/{subscription_id}?error=Failed+to+sync+subscription",
            status_code=303,
        )
