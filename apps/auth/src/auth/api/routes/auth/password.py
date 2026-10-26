# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Password reset endpoints."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_branding_service, get_db, get_email_service, get_password_service
from auth.api.schemas.api.common import MessageResponse
from auth.api.schemas.auth import ForgotPasswordRequest, ResetPasswordRequest
from auth.config import settings
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import get_tenant_context
from auth.services.branding import BrandingService
from auth.services.email import EmailService
from auth.services.email_renderer import get_email_renderer
from auth.services.password import PasswordService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

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


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Render the forgot-password HTML form.

    Serves the first step of the password reset flow: a branded HTML page
    containing an email input field. The form POSTs to `POST /auth/forgot-password`.
    No credentials are required to access this page.

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl https://auth.example.com/auth/forgot-password
    ```
    """
    logger.debug("Forgot password form requested")
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    html = await branding_service.render_template(
        db,
        "auth/forgot_password.html",
        {"request": request, "error": None, "success": None, "tenant_prefix": tenant_prefix},
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
    password_service: PasswordService = Depends(get_password_service),
    email_service: EmailService = Depends(get_email_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Submit the forgot-password form and dispatch a reset email.

    Implements the reset-request step of the password reset flow. If the
    submitted email belongs to a registered account, a single-use reset token
    is generated and emailed as a link to `GET /auth/reset-password?token=<token>`.
    To prevent account enumeration the response is identical whether or not the
    email is found — a generic success message is always displayed (NIST SP
    800-63B §5.1.1.2). The token is short-lived and invalidated after first use
    per NIST SP 800-63B §5.1.1.

    **Specification:** NIST SP 800-63B §5.1.1 (memorized secret reset), §5.1.1.2
    (account enumeration resistance)

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl -X POST -d "email=user@example.com" \\
      https://auth.example.com/auth/forgot-password
    ```
    """
    logger.info("Forgot password request for email=%s", email)
    logger.debug("Forgot password form submitted: email=%s", email)
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Try to create reset token
    result = await password_service.create_reset_token(db, email)

    if result:
        token, user_id = result
        logger.info("ACTION: password_reset_request, user_id=%s, email=%s", user_id, email)

        await dispatch_webhook_event(
            db,
            tenant_id=tenant_id,
            event=WebhookEvent.USER_PASSWORD_RESET_REQUESTED,
            data={
                "user_id": str(user_id),
                "email": email,
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
        )

        # Send reset email
        subject = "Reset your password"
        base_url = str(settings.issuer or request.base_url).rstrip("/")
        reset_url = f"{base_url}/auth/reset-password?token={token}"

        branding = await branding_service.get_branding(db, tenant_id=tenant_id)
        renderer = get_email_renderer()
        body_html, body_text = await renderer.render_email_for_tenant(
            db,
            "password_reset",
            {
                "reset_url": reset_url,
                "password_reset_expiry_hours": settings.password_reset_expiry_hours,
            },
            branding=branding,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
        await email_service.send_email(email, subject, body_html, body_text)
        await db.commit()
        logger.debug("Password reset email sent to %s", email)
    else:
        logger.debug("Forgot password: no user found for email=%s (not exposing to client)", email)

    # Always show success to prevent email enumeration
    html = await branding_service.render_template(
        db,
        "auth/forgot_password.html",
        {
            "request": request,
            "error": None,
            "success": "If an account exists with this email, a password reset link has been sent.",
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/forgot-password/api", response_model=MessageResponse)
async def forgot_password_api(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    password_service: PasswordService = Depends(get_password_service),
    email_service: EmailService = Depends(get_email_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> MessageResponse:
    """Request a password reset link via JSON API.

    JSON equivalent of `POST /auth/forgot-password` for client applications
    that do not use the server-rendered form. If the email belongs to a
    registered account, a single-use reset token is generated and emailed.
    The optional `reset_base_url` field lets proxy clients override the link
    base URL so the reset form can be served from a different origin.
    The response body is always `{"message": "..."}` regardless of whether
    the email exists, preventing account enumeration (NIST SP 800-63B §5.1.1.2).
    The reset token is single-use and expires after a configurable TTL per
    NIST SP 800-63B §5.1.1.

    **Specification:** NIST SP 800-63B §5.1.1 (memorized secret reset), §5.1.1.2
    (account enumeration resistance)

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl -X POST -H "Content-Type: application/json" \\
      -d '{"email": "user@example.com"}' \\
      https://auth.example.com/auth/forgot-password/api
    ```
    """
    logger.info("API forgot password request for email=%s", data.email)
    logger.debug("API forgot password request: email=%s", data.email)

    # Try to create reset token
    result = await password_service.create_reset_token(db, data.email)

    if result:
        token, user_id = result
        logger.info("ACTION: password_reset_request_api, user_id=%s, email=%s", user_id, data.email)

        tenant_id = get_current_tenant_id()
        await dispatch_webhook_event(
            db,
            tenant_id=tenant_id,
            event=WebhookEvent.USER_PASSWORD_RESET_REQUESTED,
            data={
                "user_id": str(user_id),
                "email": data.email,
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
        )

        # Send reset email
        subject = "Reset your password"
        # Use custom reset_base_url if provided (for client apps proxying the reset flow)
        if data.reset_base_url:
            reset_url = f"{data.reset_base_url}/auth/reset-password?token={token}"
        else:
            base_url = str(settings.issuer or request.base_url).rstrip("/")
            reset_url = f"{base_url}/auth/reset-password?token={token}"

        tenant_id = get_current_tenant_id()
        branding = await branding_service.get_branding(db, tenant_id=tenant_id)
        renderer = get_email_renderer()
        body_html, body_text = await renderer.render_email_for_tenant(
            db,
            "password_reset",
            {
                "reset_url": reset_url,
                "password_reset_expiry_hours": settings.password_reset_expiry_hours,
            },
            branding=branding,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
        await email_service.send_email(data.email, subject, body_html, body_text)
        await db.commit()
        logger.debug("API password reset email sent to %s", data.email)
    else:
        logger.debug(
            "API forgot password: no user found for email=%s (not exposing to client)", data.email
        )

    # Always return success to prevent email enumeration
    return MessageResponse(
        message="If an account exists with this email, a password reset link has been sent."
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_form(
    request: Request,
    token: str = "",
    db: AsyncSession = Depends(get_db),
    password_service: PasswordService = Depends(get_password_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Render the reset-password HTML form authenticated by a URL token.

    Serves the second step of the password reset flow. The `token` query
    parameter, embedded in the emailed link, acts as the sole credential for
    this page — no session cookie is required. The token is validated before
    rendering: an invalid or expired token returns HTTP 400 with an error page
    so the user receives clear feedback. A valid token renders the new-password
    input form which POSTs to `POST /auth/reset-password`.

    **Specification:** NIST SP 800-63B §5.1.1 (single-use token as credential)

    **Authentication:** none (token in URL query string is the credential)

    **Example:**
    ```
    curl "https://auth.example.com/auth/reset-password?token=eyJhbGciOiJIUzI1NiJ9.example"
    ```
    """
    logger.debug("Reset password form requested with token=%s", "***" if token else "(none)")
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    if not token:
        logger.warning("Reset password form: missing token")
        html = await branding_service.render_template(
            db,
            "auth/reset_password.html",
            {
                "request": request,
                "token": "",
                "error": "Invalid or missing reset token",
                "success": None,
                "valid_token": False,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    # Verify token is valid
    reset_token = await password_service.verify_reset_token(db, token)

    if not reset_token:
        logger.warning("Reset password form: invalid or expired token")
        html = await branding_service.render_template(
            db,
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "Invalid or expired reset token",
                "success": None,
                "valid_token": False,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    logger.debug("Reset password form: valid token")
    html = await branding_service.render_template(
        db,
        "auth/reset_password.html",
        {
            "request": request,
            "token": token,
            "error": None,
            "success": None,
            "valid_token": True,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/reset-password", response_class=HTMLResponse, response_model=None)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
    password_service: PasswordService = Depends(get_password_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse | RedirectResponse:
    """Submit the reset-password form and update the user credential.

    Completes the password reset flow. The form token is the single-use
    credential that authorises the credential change — it is consumed and
    invalidated on first successful use (NIST SP 800-63B §5.1.1). The new
    password must satisfy complexity requirements (min 8 chars, mixed case,
    digit). On success the user is redirected to `GET /auth/login?reset=1`;
    existing sessions are revoked server-side because the credential change
    invalidates all prior session cookies (RFC 6265 §4.1.2 security
    considerations). On failure (token expired, passwords mismatch, or
    complexity violation) the form is re-rendered with a specific error message.

    **Specification:** RFC 6265 §4.1.2 (session cookie revocation on credential
    change); NIST SP 800-63B §5.1.1 (single-use token, memorized secret policy)

    **Authentication:** none (token in form body is the credential)

    **Example:**
    ```
    curl -X POST \\
      -d "token=eyJhbGciOiJIUzI1NiJ9.example" \\
      -d "password=S3cret!pw" \\
      -d "password_confirm=S3cret!pw" \\
      https://auth.example.com/auth/reset-password
    ```
    """
    logger.info("Reset password form submitted")
    logger.debug("Reset password attempt with token")
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Validate passwords match
    if password != password_confirm:
        logger.debug("Reset password failed: passwords do not match")
        html = await branding_service.render_template(
            db,
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "Passwords do not match",
                "success": None,
                "valid_token": True,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    # Validate password strength
    try:
        ResetPasswordRequest(token=token, password=password)
    except ValueError as e:
        error_msg = str(e)
        logger.debug("Reset password failed: password validation error: %s", error_msg)
        # Extract validation error message
        if "Password must" in error_msg:
            error_msg = error_msg.split("Password must")[1]
            error_msg = f"Password must{error_msg}"
        html = await branding_service.render_template(
            db,
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": error_msg,
                "success": None,
                "valid_token": True,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    # Capture user_id before reset_password marks the token as used.
    reset_token_row = await password_service.verify_reset_token(db, token)
    reset_user_id = reset_token_row.user_id if reset_token_row else None

    # Reset password
    success = await password_service.reset_password(db, token, password)

    if not success:
        logger.warning("Reset password failed: invalid or expired token")
        html = await branding_service.render_template(
            db,
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "Invalid or expired reset token",
                "success": None,
                "valid_token": False,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    logger.info("ACTION: password_reset_complete")

    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_PASSWORD_RESET_COMPLETED,
        data={
            "user_id": str(reset_user_id) if reset_user_id else None,
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    # Redirect to login with success message
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/login?reset=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/reset-password/api", response_model=MessageResponse)
async def reset_password_api(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    password_service: PasswordService = Depends(get_password_service),
) -> MessageResponse:
    """Reset a user password via JSON API using a single-use token.

    JSON equivalent of `POST /auth/reset-password` for client applications.
    The `token` field is the single-use reset credential obtained from the
    emailed link; it is consumed and invalidated on first successful use
    (NIST SP 800-63B §5.1.1). The new password must satisfy complexity
    requirements (min 8 chars, mixed case, digit) and is stored hashed with
    a memory-hard algorithm per NIST SP 800-63B §5.1.1.2. Existing sessions
    for the affected user are revoked on credential change (RFC 6265 §4.1.2).
    Returns HTTP 400 if the token is invalid, already used, or expired.

    **Specification:** RFC 6265 §4.1.2 (session revocation on credential change);
    NIST SP 800-63B §5.1.1 (single-use token, memorized secret storage)

    **Authentication:** none (token in request body is the credential)

    **Example:**
    ```
    curl -X POST -H "Content-Type: application/json" \\
      -d '{"token": "eyJhbGciOiJIUzI1NiJ9.example", "password": "S3cret!pw"}' \\
      https://auth.example.com/auth/reset-password/api
    ```
    """
    logger.info("API reset password request")
    logger.debug("API reset password attempt with token")

    reset_token_row = await password_service.verify_reset_token(db, data.token)
    reset_user_id = reset_token_row.user_id if reset_token_row else None

    success = await password_service.reset_password(db, data.token, data.password)

    if not success:
        logger.warning("API reset password failed: invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    logger.info("ACTION: password_reset_complete_api")

    tenant_id = get_current_tenant_id()
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_PASSWORD_RESET_COMPLETED,
        data={
            "user_id": str(reset_user_id) if reset_user_id else None,
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    return MessageResponse(message="Password reset successfully")
