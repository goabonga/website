# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler dashboard routes for HTML pages.

Scopes required:
- mailler:stats - View mailler statistics dashboard
- mailler:read - View emails list and details
- mailler:admin - Manage the authorized clients of the mailler service
"""

from datetime import date, timedelta
from urllib.parse import quote, quote_plus
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Path, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import require_resource_scopes_or_redirect
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services.mailler_client import MaillerAPIError, mailler_client

router = APIRouter(prefix="/mailler", tags=["mailler"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

# Request mailler scopes for the dashboard
require_mailler_read = require_resource_scopes_or_redirect(
    "mailler", extra_scopes=["mailler:admin", "vpn:admin", "billing:read"]
)
# The admin scope is not one of the resource scopes: it must be requested to be granted
require_mailler_admin = require_resource_scopes_or_redirect(
    "mailler",
    required_scope="mailler:admin",
    extra_scopes=["mailler:admin", "vpn:admin", "billing:read"],
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


# =============================================================================
# Authorized clients
# =============================================================================


def parse_senders(text: str) -> list[dict[str, str]]:
    """Read the extra sender identities of a form: one ``address`` or ``address, name`` per line.

    Raises:
        ValueError: If a line has no address.
    """
    senders: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        address, _, name = line.partition(",")
        address = address.strip()
        if not address or " " in address:
            raise ValueError(
                f"'{line.strip()}' is not a sender: write an address, then an optional name"
            )
        sender = {"email": address}
        if name.strip():
            sender["name"] = name.strip()
        senders.append(sender)
    return senders


def parse_limit(text: str, label: str) -> int | None:
    """Read a sending limit of a form: a positive whole number, or nothing for no limit.

    Raises:
        ValueError: If the text is not a positive whole number.
    """
    value = text.strip()
    if not value:
        return None
    if not value.isdigit() or int(value) < 1:
        raise ValueError(f"{label} must be a positive whole number")
    return int(value)


def client_payload(
    *,
    name: str,
    from_email: str,
    from_name: str,
    reply_to: str,
    allowed_senders: str,
    allowed_providers: list[str],
    default_provider: str,
    rate_limit_per_minute: str,
    daily_quota: str,
    callback_url: str,
    callback_secret: str,
    is_active: bool,
    updating: bool,
) -> dict:
    """Build the body sent to the client registry from the fields of a form.

    When registering, empty fields are left out. When updating, they are sent as ``null`` so that
    emptying a field removes the value, except the callback secret, which is write-only: an empty
    field keeps the secret unless the callback URL is emptied too.

    Raises:
        ValueError: If a sender or a limit is malformed.
    """
    callback_url = callback_url.strip()
    payload: dict = {
        "name": name.strip() or None,
        "is_active": is_active,
        "from_email": from_email.strip() or None,
        "from_name": from_name.strip() or None,
        "reply_to": reply_to.strip() or None,
        "allowed_senders": parse_senders(allowed_senders),
        "allowed_providers": [provider for provider in allowed_providers if provider],
        "default_provider": default_provider.strip() or None,
        "rate_limit_per_minute": parse_limit(rate_limit_per_minute, "The rate limit"),
        "daily_quota": parse_limit(daily_quota, "The daily quota"),
        "callback_url": callback_url or None,
    }
    if callback_secret:
        payload["callback_secret"] = callback_secret
    elif updating and not callback_url:
        payload["callback_secret"] = None
    if not updating:
        payload = {key: value for key, value in payload.items() if value is not None}
    return payload


def _clients_redirect(path: str, key: str, message: str) -> RedirectResponse:
    """Redirect to ``path`` with a ``success`` or ``error`` banner."""
    return RedirectResponse(url=f"{path}?{key}={quote_plus(message[:300])}", status_code=303)


@router.get("/clients", response_class=HTMLResponse)
async def clients_list(
    request: Request,
    page: int = Query(default=1, ge=1),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|inactive)$"),
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """List the clients authorized to use the mailler service."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    logger.info(
        "Mailler clients accessed | user_id=%s page=%d search=%s status=%s",
        user.id,
        page,
        search,
        status,
    )

    data = await mailler_client.list_clients(
        page=page,
        page_size=settings.mailler_clients_page_size,
        is_active=None if status is None else status == "active",
        search=search,
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/mailler/clients.html",
        context={
            "request": request,
            "active_section": "mailler",
            "user": user,
            "clients": data.get("items", []),
            "total": data.get("total", 0),
            "page": data.get("page", 1),
            "pages": data.get("pages", 1),
            "search": search,
            "status_filter": status,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


async def _client_form(request: Request, user: User, client: dict | None):
    """Render the form that registers or edits a client."""
    return templates.TemplateResponse(
        request=request,
        name="admin/mailler/client_form.html",
        context={
            "request": request,
            "active_section": "mailler",
            "user": user,
            "client": client,
            "is_edit": client is not None,
            "providers": await mailler_client.get_providers(),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/clients/new", response_class=HTMLResponse)
async def client_new(
    request: Request,
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Form to register a client."""
    if not isinstance(auth_result, User):
        return auth_result

    return await _client_form(request, auth_result, None)


@router.post("/clients/new")
async def client_create(
    request: Request,
    client_id: str = Form(...),
    name: str = Form(""),
    is_active: bool = Form(False),
    from_email: str = Form(""),
    from_name: str = Form(""),
    reply_to: str = Form(""),
    allowed_senders: str = Form(""),
    allowed_providers: list[str] = Form([]),
    default_provider: str = Form(""),
    rate_limit_per_minute: str = Form(""),
    daily_quota: str = Form(""),
    callback_url: str = Form(""),
    callback_secret: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Register a client."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    client_id = client_id.strip()
    if not client_id or any(character.isspace() for character in client_id):
        return _clients_redirect(
            "/mailler/clients/new", "error", "A client id has no spaces and is not empty"
        )

    try:
        payload = client_payload(
            name=name,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            allowed_senders=allowed_senders,
            allowed_providers=allowed_providers,
            default_provider=default_provider,
            rate_limit_per_minute=rate_limit_per_minute,
            daily_quota=daily_quota,
            callback_url=callback_url,
            callback_secret=callback_secret,
            is_active=is_active,
            updating=False,
        )
        created = await mailler_client.create_client({"client_id": client_id, **payload})
    except (ValueError, MaillerAPIError) as error:
        return _clients_redirect(
            "/mailler/clients/new", "error", str(getattr(error, "message", error))
        )

    if not created:
        return _clients_redirect(
            "/mailler/clients/new", "error", "The mailler service did not answer"
        )

    logger.info(
        "Mailler client registered | user_id=%s registered_client_id=%s", user.id, client_id
    )
    return _clients_redirect("/mailler/clients", "success", f"Client {client_id} registered")


@router.get("/clients/{client_id}/edit", response_class=HTMLResponse)
async def client_edit(
    request: Request,
    client_id: str,
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Form to edit a client."""
    if not isinstance(auth_result, User):
        return auth_result

    client = await mailler_client.get_client(client_id)
    if not client:
        return _clients_redirect("/mailler/clients", "error", "Client not found")

    return await _client_form(request, auth_result, client)


@router.post("/clients/{client_id}/edit")
async def client_update(
    request: Request,
    client_id: str,
    name: str = Form(""),
    is_active: bool = Form(False),
    from_email: str = Form(""),
    from_name: str = Form(""),
    reply_to: str = Form(""),
    allowed_senders: str = Form(""),
    allowed_providers: list[str] = Form([]),
    default_provider: str = Form(""),
    rate_limit_per_minute: str = Form(""),
    daily_quota: str = Form(""),
    callback_url: str = Form(""),
    callback_secret: str = Form(""),
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Update a client: every field of the form is applied, an empty one removes the value."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    edit_path = f"/mailler/clients/{quote(client_id, safe='')}/edit"

    try:
        payload = client_payload(
            name=name,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            allowed_senders=allowed_senders,
            allowed_providers=allowed_providers,
            default_provider=default_provider,
            rate_limit_per_minute=rate_limit_per_minute,
            daily_quota=daily_quota,
            callback_url=callback_url,
            callback_secret=callback_secret,
            is_active=is_active,
            updating=True,
        )
        updated = await mailler_client.update_client(client_id, payload)
    except (ValueError, MaillerAPIError) as error:
        return _clients_redirect(edit_path, "error", str(getattr(error, "message", error)))

    if not updated:
        return _clients_redirect(edit_path, "error", "The mailler service did not answer")

    logger.info("Mailler client updated | user_id=%s updated_client_id=%s", user.id, client_id)
    return _clients_redirect("/mailler/clients", "success", f"Client {client_id} updated")


async def _set_client_activation(client_id: str, active: bool, user: User) -> RedirectResponse:
    """Activate or deactivate a client, and say what happened."""
    verb = "activated" if active else "deactivated"
    try:
        updated = await mailler_client.update_client(client_id, {"is_active": active})
    except MaillerAPIError as error:
        return _clients_redirect("/mailler/clients", "error", error.message)
    if not updated:
        return _clients_redirect("/mailler/clients", "error", "The mailler service did not answer")
    logger.info("Mailler client %s | user_id=%s changed_client_id=%s", verb, user.id, client_id)
    return _clients_redirect("/mailler/clients", "success", f"Client {client_id} {verb}")


@router.post("/clients/{client_id}/deactivate")
async def client_deactivate(
    request: Request,
    client_id: str,
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Deactivate a client: the mailler service refuses it from then on and stops its work."""
    if not isinstance(auth_result, User):
        return auth_result

    return await _set_client_activation(client_id, False, auth_result)


@router.post("/clients/{client_id}/activate")
async def client_activate(
    request: Request,
    client_id: str,
    auth_result: User | RedirectResponse = Depends(require_mailler_admin),
):
    """Activate a client again."""
    if not isinstance(auth_result, User):
        return auth_result

    return await _set_client_activation(client_id, True, auth_result)
