# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 Device Authorization endpoint (RFC 8628)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from auth.api.deps import (
    get_branding_service,
    get_db,
    get_device_code_service,
    get_oauth2_client_service,
    get_session_service,
)
from auth.api.schemas.oauth2 import (
    DeviceAuthorizationResponse,
    OAuth2Error,
    TokenErrorResponse,
)
from auth.config import settings
from auth.db.models.oauth2 import DeviceCodeStatus
from auth.middlewares.tenant import get_session_cookie_name, get_tenant_context
from auth.services.branding import BrandingService
from auth.services.device_code import DeviceCodeService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.session import SessionService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tenant_prefix() -> str:
    """Get the URL prefix for the current tenant if resolved via path.

    Returns:
        The tenant prefix (e.g., '/t/knowledge') if using path resolution,
        or empty string otherwise.
    """
    tenant_ctx = get_tenant_context()
    if tenant_ctx and tenant_ctx.tenant_slug and tenant_ctx.resolution_method == "path":
        return f"/t/{tenant_ctx.tenant_slug}"
    return ""


def get_current_tenant_id():
    """Get the current tenant ID from context."""
    tenant_ctx = get_tenant_context()
    return tenant_ctx.tenant_id if tenant_ctx else None


# Device authorization grant type
DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def _device_error(error: str, description: str) -> HTTPException:
    """Create a device authorization error response."""
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=TokenErrorResponse(
            error=error,
            error_description=description,
        ).model_dump(),
    )


@router.post(
    "/device",
    response_model=DeviceAuthorizationResponse,
    responses={400: {"model": TokenErrorResponse}},
)
async def device_authorization(
    request: Request,
    client_id: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth2_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
    device_service: Annotated[DeviceCodeService, Depends(get_device_code_service)],
    scope: Annotated[str | None, Form()] = None,
) -> DeviceAuthorizationResponse:
    """Issue a device code and user code to begin the Device Authorization Grant.

    This implements RFC 8628 §3.1–§3.2: the device posts its `client_id` and
    optional `scope` to receive a `device_code`, a short `user_code`, a
    `verification_uri` the end-user must visit on a separate browser, and a
    `verification_uri_complete` that encodes the user code for QR-code flows.
    The device must then poll `POST /oauth2/token` with
    `grant_type=urn:ietf:params:oauth:grant-type:device_code` at no faster
    than the returned `interval` (seconds) until the user approves or the
    `expires_in` window lapses.

    **Specification:** RFC 8628 §3.1 (Device Authorization Request), §3.2
    (Device Authorization Response)

    **Authentication:** Client authentication per RFC 6749 §2.3. Public clients
    supply only `client_id`; confidential clients must authenticate with their
    client secret. No user session is required at this step.

    **Responses:**
    - `200` — device code issued; poll token endpoint at `interval` seconds
    - `400 invalid_client` — unknown or inactive client
    - `400 unauthorized_client` — client not permitted for device flow
    - `400 invalid_scope` — one or more requested scopes not allowed for client

    **Example:**
    ```
    curl -X POST https://auth.example.com/oauth2/device \\
      -d "client_id=myapp-device-client" \\
      -d "scope=openid profile email"
    ```
    """
    logger.info("Device authorization request: client_id=%s", client_id)

    # Get client
    client = await oauth2_service.get_client_by_client_id(db, client_id)
    if not client or not client.is_active:
        logger.warning("Device authorization failed: invalid client %s", client_id)
        raise _device_error(OAuth2Error.INVALID_CLIENT, "Invalid client")

    # Validate grant type
    if not oauth2_service.validate_grant_type(client, DEVICE_CODE_GRANT_TYPE):
        logger.warning(
            "Device authorization failed: client %s not authorized for device flow", client_id
        )
        raise _device_error(
            OAuth2Error.UNAUTHORIZED_CLIENT,
            "Client is not authorized for device authorization",
        )

    # Parse and validate scopes
    requested_scopes = scope.split() if scope else []
    if requested_scopes and not oauth2_service.validate_scopes(client, requested_scopes):
        logger.warning("Device authorization failed: invalid scope for client %s", client_id)
        raise _device_error(OAuth2Error.INVALID_SCOPE, "Invalid scope")

    # Use allowed scopes if none requested
    if not requested_scopes:
        requested_scopes = list(client.allowed_scopes)

    # Build verification URI
    base_url = str(request.base_url).rstrip("/")
    verification_uri = f"{base_url}/oauth2/device/verify"

    # Create device authorization
    try:
        device_code, device = await device_service.create_device_authorization(
            db=db,
            client=client,
            scopes=requested_scopes,
            verification_uri=verification_uri,
        )
    except ValueError as e:
        logger.error("Device authorization failed: %s", e)
        raise _device_error(OAuth2Error.SERVER_ERROR, str(e))

    # Calculate expires_in
    expires_in = settings.device_code_expiry_minutes * 60

    # Build verification URI complete
    verification_uri_complete = f"{verification_uri}?user_code={device.user_code}"

    logger.info(
        "Device authorization created: client_id=%s, user_code=%s", client_id, device.user_code
    )
    return DeviceAuthorizationResponse(
        device_code=device_code,
        user_code=device.user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=expires_in,
        interval=device.interval,
    )


@router.get("/device/verify", response_class=HTMLResponse)
async def device_verify_form(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
    user_code: str | None = None,
) -> Response:
    """Render the user-facing device verification page (RFC 8628 §3.3).

    This is the page the end-user opens on their browser after the device
    displays a `verification_uri`. It shows a form where the user enters the
    short `user_code` shown on the device screen. An optional `user_code`
    query parameter pre-populates the form, supporting the
    `verification_uri_complete` QR-code flow described in RFC 8628 §3.3.2.
    If the user is not authenticated a redirect to the login page is issued
    first, preserving the current URL as the `next` parameter so the user
    returns here after sign-in.

    **Specification:** RFC 8628 §3.3 (User Interaction), §3.3.2
    (Non-Textual Verification URI)

    **Authentication:** Session cookie required. Unauthenticated requests are
    redirected to `GET /auth/login?next=<this-url>`.

    **Example:**
    ```
    # Direct browser navigation (user types the code manually)
    curl -b "session=<cookie>" \\
      https://auth.example.com/oauth2/device/verify

    # Pre-filled form via verification_uri_complete (QR-code scan)
    curl -b "session=<cookie>" \\
      "https://auth.example.com/oauth2/device/verify?user_code=ABCD-1234"
    ```
    """
    logger.debug("Device verification form requested")
    session = request.cookies.get(get_session_cookie_name())
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Build the current URL with proxy headers and tenant prefix restored
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    path = f"{tenant_prefix}{request.url.path}"
    current_url = f"{scheme}://{host}{path}"
    if request.url.query:
        current_url += f"?{request.url.query}"

    # Check if user is authenticated
    if not session:
        logger.debug("Device verification: user not authenticated, redirecting to login")
        login_url = f"{tenant_prefix}/auth/login?next={current_url}"
        return RedirectResponse(url=login_url, status_code=status.HTTP_302_FOUND)

    session_record = await session_service.get_session(db, session)
    if not session_record:
        logger.debug("Device verification: invalid session, redirecting to login")
        login_url = f"{tenant_prefix}/auth/login?next={current_url}"
        return RedirectResponse(url=login_url, status_code=status.HTTP_302_FOUND)

    html = await branding_service.render_template(
        db,
        "oauth2/device.html",
        {
            "request": request,
            "user_code": user_code or "",
            "error": None,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/device/verify", response_class=HTMLResponse)
async def device_verify_code(
    request: Request,
    user_code: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    device_service: Annotated[DeviceCodeService, Depends(get_device_code_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Validate a submitted user code and present the consent screen.

    This is the POST handler for the verification form (RFC 8628 §3.3). The
    user submits the `user_code` they read off the device display. The server
    validates the code against pending device authorizations: expired codes
    and already-used codes are rejected with an inline error. For clients that
    do not require explicit consent (`require_consent=False`) the device is
    immediately authorized and the completion page is shown, saving the user
    an extra click. For all other clients the consent screen listing the
    application name and requested scopes is rendered so the user can approve
    or deny the device.

    **Specification:** RFC 8628 §3.3 (User Interaction), §3.3.1 (User Code
    Confirmation)

    **Authentication:** Session cookie required. Unauthenticated requests are
    redirected to `GET /auth/login?next=/oauth2/device/verify`.

    **Responses:**
    - `200` — consent form or auto-authorized completion page (HTML)
    - `302` — redirect to login when session is absent or invalid

    **Example:**
    ```
    curl -X POST https://auth.example.com/oauth2/device/verify \\
      -b "session=<cookie>" \\
      -d "user_code=ABCD-1234"
    ```
    """
    logger.info("Device code verification: user_code=%s", user_code)
    session = request.cookies.get(get_session_cookie_name())
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Check authentication
    if not session:
        logger.debug("Device verification: user not authenticated")
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/login?next={tenant_prefix}/oauth2/device/verify",
            status_code=status.HTTP_302_FOUND,
        )

    session_record = await session_service.get_session(db, session)
    if not session_record:
        logger.debug("Device verification: invalid session")
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/login?next={tenant_prefix}/oauth2/device/verify",
            status_code=status.HTTP_302_FOUND,
        )

    # Look up device code
    device = await device_service.get_by_user_code(db, user_code)

    if not device:
        logger.warning("Device verification failed: invalid user_code %s", user_code)
        html = await branding_service.render_template(
            db,
            "oauth2/device.html",
            {
                "request": request,
                "user_code": user_code,
                "error": "Invalid code. Please check and try again.",
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    if device_service.is_expired(device):
        logger.warning("Device verification failed: expired user_code %s", user_code)
        html = await branding_service.render_template(
            db,
            "oauth2/device.html",
            {
                "request": request,
                "user_code": user_code,
                "error": "This code has expired. Please request a new one.",
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    if device.status != DeviceCodeStatus.PENDING.value:
        logger.warning("Device verification failed: user_code %s already used", user_code)
        html = await branding_service.render_template(
            db,
            "oauth2/device.html",
            {
                "request": request,
                "user_code": user_code,
                "error": "This code has already been used.",
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    # Load client for display
    await db.refresh(device, ["client"])

    # If client doesn't require consent, auto-authorize
    if not device.client.require_consent:
        logger.debug(
            "Device verification: auto-authorizing (consent not required) for user_code %s",
            user_code,
        )
        await device_service.authorize(db, device, session_record.user_id)
        html = await branding_service.render_template(
            db,
            "oauth2/device_complete.html",
            {
                "request": request,
                "message": "Device authorized successfully! You can close this window.",
                "success": True,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    logger.debug("Device verification: showing consent form for user_code %s", user_code)
    # Show consent form
    html = await branding_service.render_template(
        db,
        "oauth2/device_consent.html",
        {
            "request": request,
            "user_code": device.user_code,
            "client_name": device.client.name,
            "scopes": device.scopes,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/device/complete", response_class=HTMLResponse)
async def device_complete(
    request: Request,
    user_code: Annotated[str, Form()],
    consent: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    device_service: Annotated[DeviceCodeService, Depends(get_device_code_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Record the user's consent decision and finalize device authorization.

    This is the final step of the user-interaction phase (RFC 8628 §3.3).
    The consent form posts `user_code` and `consent` (`allow` or `deny`).
    On `allow` the device code record is transitioned to the authorized state,
    unblocking the device's polling loop at `POST /oauth2/token`; the device
    will receive an access token on its next poll. On `deny` the device code
    is transitioned to the denied state and the device will receive an
    `access_denied` error from the token endpoint. Either way the user sees a
    completion page confirming the outcome and is told the browser window can
    be closed.

    **Specification:** RFC 8628 §3.3 (User Interaction), §3.4 (Device Access
    Token Request — outcome observed by device after this step)

    **Authentication:** Session cookie required. Unauthenticated requests are
    redirected to `GET /auth/login?next=/oauth2/device/verify`.

    **Responses:**
    - `200` — completion page confirming authorization or denial (HTML)
    - `302` — redirect to login when session is absent or invalid

    **Example:**
    ```
    # User approves the device
    curl -X POST https://auth.example.com/oauth2/device/complete \\
      -b "session=<cookie>" \\
      -d "user_code=ABCD-1234&consent=allow"

    # User denies the device
    curl -X POST https://auth.example.com/oauth2/device/complete \\
      -b "session=<cookie>" \\
      -d "user_code=ABCD-1234&consent=deny"
    ```
    """
    logger.info("Device authorization completion: user_code=%s, consent=%s", user_code, consent)
    session = request.cookies.get(get_session_cookie_name())
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Check authentication
    if not session:
        logger.debug("Device completion: user not authenticated")
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/login?next={tenant_prefix}/oauth2/device/verify",
            status_code=status.HTTP_302_FOUND,
        )

    session_record = await session_service.get_session(db, session)
    if not session_record:
        logger.debug("Device completion: invalid session")
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/login?next={tenant_prefix}/oauth2/device/verify",
            status_code=status.HTTP_302_FOUND,
        )

    # Look up device code
    device = await device_service.get_by_user_code(db, user_code)

    if not device or device_service.is_expired(device):
        logger.warning("Device completion failed: invalid or expired user_code %s", user_code)
        html = await branding_service.render_template(
            db,
            "oauth2/device.html",
            {
                "request": request,
                "user_code": user_code,
                "error": "Invalid or expired code.",
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    if device.status != DeviceCodeStatus.PENDING.value:
        logger.warning("Device completion failed: user_code %s already used", user_code)
        html = await branding_service.render_template(
            db,
            "oauth2/device.html",
            {
                "request": request,
                "user_code": user_code,
                "error": "This code has already been used.",
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    # Process consent decision
    if consent == "allow":
        await device_service.authorize(db, device, session_record.user_id)
        message = "Device authorized successfully! You can close this window."
        success = True
        logger.info(
            "Device authorized: user_code=%s, user_id=%s", user_code, session_record.user_id
        )
    else:
        await device_service.deny(db, device)
        message = "Authorization denied. You can close this window."
        success = False
        logger.info("Device authorization denied: user_code=%s", user_code)

    html = await branding_service.render_template(
        db,
        "oauth2/device_complete.html",
        {
            "request": request,
            "message": message,
            "success": success,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)
