# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Email verification endpoints."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_branding_service, get_db, get_email_service, get_user_service
from auth.api.schemas.api.common import MessageResponse
from auth.api.schemas.auth import ResendVerificationRequest, VerifyEmailRequest
from auth.config import settings
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import get_tenant_context
from auth.services.branding import BrandingService
from auth.services.email import EmailService
from auth.services.user import UserService
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


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    branding_service: BrandingService = Depends(get_branding_service),
    email: str = "",
    next: str = "",
) -> HTMLResponse:
    """Render the email verification code entry page.

    This is the HTML variant of the verification flow. It displays a form
    where the user enters the one-time code that was emailed to them. The
    optional `email` query parameter pre-fills the email field, and `next`
    carries the post-verification redirect target through the flow.

    **Authentication:** none (public HTML page)

    **Example:**
    ```
    curl 'https://auth.example.com/auth/verify-email?email=user%40example.com&next=%2Fdashboard'
    ```
    """
    logger.debug("Email verification form requested for email=%s", email)
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    html = await branding_service.render_template(
        db,
        "auth/verify_email.html",
        {
            "request": request,
            "email": email,
            "error": None,
            "success": None,
            "next": next,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/verify-email", response_class=HTMLResponse, response_model=None)
async def verify_email_submit(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    next: str = Form(""),
    db: AsyncSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse | RedirectResponse:
    """Submit the email verification code via the HTML form.

    This is the HTML form-post variant of the verification flow. The
    submitted `code` is a single-use, time-limited token that was delivered
    by email; it is consumed immediately on success and cannot be reused. On
    successful verification the user's email is marked as verified, a
    `USER_EMAIL_VERIFIED` webhook event is dispatched, and the browser is
    redirected to `/auth/login?verified=1` (preserving any `next` parameter).
    On failure the form is re-rendered with an error message and HTTP 400.

    **Authentication:** none (the emailed code is the credential)

    **Responses:**
    - `303` — code accepted; redirects to login page
    - `400` — invalid or expired verification code

    **Example:**
    ```
    curl -X POST https://auth.example.com/auth/verify-email \\
      -d 'email=user%40example.com&code=123456&next=%2Fdashboard'
    ```
    """
    logger.info("Email verification attempt for email=%s", email)
    logger.debug("Email verification form submitted: email=%s", email)
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Verify the code
    success = await email_service.verify_code(db, email, code)

    if not success:
        logger.warning("Email verification failed: invalid or expired code for email=%s", email)
        html = await branding_service.render_template(
            db,
            "auth/verify_email.html",
            {
                "request": request,
                "email": email,
                "error": "Invalid or expired verification code",
                "success": None,
                "next": next,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    logger.info("ACTION: email_verify, email=%s", email)

    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_EMAIL_VERIFIED,
        data={"email": email, "tenant_id": str(tenant_id) if tenant_id else None},
    )
    await db.commit()

    # Redirect to login with success message, preserving next parameter
    login_params = {"verified": "1"}
    if next:
        login_params["next"] = next
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/login?{urlencode(login_params)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/verify-email/api", response_model=MessageResponse)
async def verify_email_api(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    email_service: EmailService = Depends(get_email_service),
) -> MessageResponse:
    """Verify an email address using a one-time code (JSON API).

    This is the machine-readable JSON variant of the verification flow,
    intended for SPA and mobile clients. The `code` field must match the
    single-use, time-limited token delivered to the supplied `email`; the
    token is consumed immediately and cannot be reused. On success the
    user's email is marked as verified, a `USER_EMAIL_VERIFIED` webhook
    event is dispatched, and `{"message": "Email verified successfully"}` is
    returned. There is no formal specification for this flow; treat the code
    as an opaque credential.

    **Authentication:** none (the emailed code is the credential)

    **Responses:**
    - `200` — email verified; returns `{"message": "Email verified successfully"}`
    - `400` — invalid or expired verification code

    **Example:**
    ```
    curl -X POST https://auth.example.com/auth/verify-email/api \\
      -H 'Content-Type: application/json' \\
      -d '{"email": "user@example.com", "code": "123456"}'
    ```
    """
    logger.info("API email verification attempt for email=%s", data.email)
    logger.debug("API email verification request: email=%s", data.email)

    success = await email_service.verify_code(db, data.email, data.code)

    if not success:
        logger.warning(
            "API email verification failed: invalid or expired code for email=%s", data.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    logger.info("ACTION: email_verify_api, email=%s", data.email)

    tenant_id = get_current_tenant_id()
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_EMAIL_VERIFIED,
        data={"email": data.email, "tenant_id": str(tenant_id) if tenant_id else None},
    )
    await db.commit()

    return MessageResponse(message="Email verified successfully")


@router.post("/resend-verification", response_class=HTMLResponse)
async def resend_verification_submit(
    request: Request,
    email: str = Form(...),
    next: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    email_service: EmailService = Depends(get_email_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Re-send the email verification code via the HTML form.

    This is the HTML form-post variant of the resend flow. A fresh
    single-use, time-limited verification code is generated and emailed when
    an account matching the supplied address exists. To prevent email
    enumeration the response is always HTTP 200 with a generic success
    message, regardless of whether the address is registered. Callers should
    apply their own rate-limiting before hitting this endpoint repeatedly.

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl -X POST https://auth.example.com/auth/resend-verification \\
      -d 'email=user%40example.com&next=%2Fdashboard'
    ```
    """
    logger.info("Resend verification email request for email=%s", email)
    logger.debug("Resend verification form submitted: email=%s", email)
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Find user by email
    user = await user_service.get_by_email(db, email)

    if user:
        logger.info("ACTION: resend_verification, user_id=%s, email=%s", user.id, email)
        # Send verification email with link
        base_url = str(request.base_url).rstrip("/")
        await email_service.send_verification_email(
            db,
            str(user.id),
            email,
            base_url=base_url,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
    else:
        logger.debug(
            "Resend verification: no user found for email=%s (not exposing to client)", email
        )

    # Always show success to prevent email enumeration
    html = await branding_service.render_template(
        db,
        "auth/verify_email.html",
        {
            "request": request,
            "email": email,
            "error": None,
            "success": "If an account exists with this email, a verification code has been sent.",
            "next": next,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/resend-verification/api", response_model=MessageResponse)
async def resend_verification_api(
    data: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    email_service: EmailService = Depends(get_email_service),
) -> MessageResponse:
    """Re-send the email verification code (JSON API).

    This is the machine-readable JSON variant of the resend flow, intended
    for SPA and mobile clients. A fresh single-use, time-limited
    verification code is generated and emailed when an account matching
    `email` exists. To prevent email enumeration the response is always
    HTTP 200 with a generic success message, regardless of whether the
    address is registered. Callers are expected to enforce their own
    client-side rate-limiting to avoid flooding the mail delivery service.

    **Authentication:** none (public endpoint)

    **Responses:**
    - `200` — always returns the same generic message to prevent enumeration

    **Example:**
    ```
    curl -X POST https://auth.example.com/auth/resend-verification/api \\
      -H 'Content-Type: application/json' \\
      -d '{"email": "user@example.com"}'
    ```
    """
    logger.info("API resend verification email request for email=%s", data.email)
    logger.debug("API resend verification request: email=%s", data.email)
    tenant_id = get_current_tenant_id()

    # Find user by email
    user = await user_service.get_by_email(db, data.email)

    if user:
        logger.info("ACTION: resend_verification_api, user_id=%s, email=%s", user.id, data.email)
        # Send verification email with link (use issuer as base_url for API calls)
        await email_service.send_verification_email(
            db,
            str(user.id),
            data.email,
            base_url=settings.issuer,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
    else:
        logger.debug(
            "API resend verification: no user found for email=%s (not exposing to client)",
            data.email,
        )

    # Always return success to prevent email enumeration
    return MessageResponse(
        message="If an account exists with this email, a verification code has been sent."
    )
