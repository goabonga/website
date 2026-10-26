# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MFA endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_branding_service,
    get_db,
    get_email_service,
    get_mfa_service,
    get_session_service,
)
from auth.api.schemas.api.common import MessageResponse
from auth.api.schemas.mfa import (
    BackupCodesResponse,
    EmailMFASendResponse,
    MFAStatusResponse,
    MFAVerifyRequest,
    TOTPEnableResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
)
from auth.config import settings
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import get_session_cookie_name, get_tenant_context
from auth.services.branding import BrandingService
from auth.services.email import EmailService
from auth.services.mfa import MFAService
from auth.services.session import SessionService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mfa")


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


async def _get_current_user_id(
    request: Request,
    db: AsyncSession,
    session_service: SessionService,
) -> str:
    """Get current user ID from session."""
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = await session_service.get_user_by_session_token(db, session_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    return str(user.id)


async def _get_current_user_email(
    request: Request,
    db: AsyncSession,
    session_service: SessionService,
) -> tuple[str, str]:
    """Get current user ID and email from session."""
    from auth.services.auth import AuthService

    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = await session_service.get_user_by_session_token(db, session_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    auth_service = AuthService()
    email = await auth_service.get_user_primary_email(db, str(user.id))

    return str(user.id), email or "user"


@router.get("/status")
async def get_mfa_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> MFAStatusResponse:
    """Return TOTP enablement state and backup code counts for the current user.

    Reads the authenticated user's MFA record and reports whether TOTP is
    active. When TOTP is enabled, the response also includes the total number
    of backup codes issued and how many have not yet been consumed. Backup
    codes are single-use; each successful use marks the code as spent in the
    database so it cannot be replayed.

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/status
    ```
    """
    logger.debug("MFA status request")
    user_id = await _get_current_user_id(request, db, session_service)

    user_mfa = await mfa_service.get_user_mfa(db, user_id)

    if not user_mfa or not user_mfa.totp_enabled:
        logger.debug("MFA status: TOTP not enabled for user_id=%s", user_id)
        return MFAStatusResponse(totp_enabled=False)

    status_result = await mfa_service.get_backup_codes_status(db, user_id)
    logger.debug("MFA status: TOTP enabled for user_id=%s", user_id)

    return MFAStatusResponse(
        totp_enabled=True,
        backup_codes_remaining=status_result[0] if status_result else None,
        backup_codes_total=status_result[1] if status_result else None,
    )


@router.post("/totp/setup")
async def setup_totp(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> TOTPSetupResponse:
    """Initialise TOTP enrolment for the current user.

    Generates a fresh TOTP secret (RFC 6238 / RFC 4226 HMAC-SHA1 core) bound
    to the user's primary email address and persists it as a pending secret —
    TOTP is not yet active until the user completes verification via
    `POST /auth/mfa/totp/verify`. Returns the raw Base32 secret and a
    Base64-encoded PNG of the provisioning QR code for import into an
    authenticator app. Calling this endpoint while TOTP is already enabled
    returns `400`; use `POST /auth/mfa/setup/reconfigure` instead.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/totp/setup
    ```
    """
    logger.info("TOTP setup request")
    user_id, email = await _get_current_user_email(request, db, session_service)

    # Check if already enabled
    user_mfa = await mfa_service.get_user_mfa(db, user_id)
    if user_mfa and user_mfa.totp_enabled:
        logger.warning("TOTP setup failed: already enabled for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is already enabled. Disable it first.",
        )

    secret, uri, qr_code = await mfa_service.setup_totp(db, user_id, email)
    await db.commit()

    logger.info("ACTION: mfa_totp_setup, user_id=%s", user_id)

    return TOTPSetupResponse(
        secret=secret,
        qr_code=qr_code,
    )


@router.post("/totp/verify")
async def verify_and_enable_totp(
    request: Request,
    data: TOTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> TOTPEnableResponse:
    """Confirm the pending TOTP secret and activate TOTP for the current user.

    Validates the 6-digit TOTP code (RFC 6238) against the secret stored
    during setup. On success, TOTP is marked active and a fresh set of
    single-use backup codes is generated and returned — store them safely as
    each code can only be used once. Two webhook events are fired atomically:
    `mfa.enabled` and `mfa.backup_codes_generated`. Submitting an incorrect
    code or calling before setup returns `400`.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "123456"}' \\
      https://auth.example.com/auth/mfa/totp/verify
    ```
    """
    logger.info("TOTP verify and enable request")
    user_id = await _get_current_user_id(request, db, session_service)

    backup_codes = await mfa_service.enable_totp(db, user_id, data.code)

    if backup_codes is None:
        logger.warning("TOTP enable failed: invalid code for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not set up",
        )

    tenant_id = get_current_tenant_id()
    mfa_data = {"user_id": user_id, "tenant_id": tenant_id, "method": "totp"}
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.MFA_ENABLED, data=mfa_data
    )
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.MFA_BACKUP_CODES_GENERATED,
        data={**mfa_data, "count": len(backup_codes)},
    )
    await db.commit()

    logger.info("ACTION: mfa_totp_enable, user_id=%s", user_id)

    return TOTPEnableResponse(
        message="TOTP enabled successfully",
        backup_codes=backup_codes,
    )


@router.post("/totp/disable", response_model=MessageResponse)
async def disable_totp(
    request: Request,
    data: TOTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> MessageResponse:
    """Deactivate TOTP for the current user after confirming the current code.

    Requires a valid 6-digit TOTP code (RFC 6238) as proof of possession
    before disabling. This prevents an attacker with only a stolen session
    cookie from silently removing MFA. On success, all stored backup codes are
    also invalidated and a `mfa.disabled` webhook event is dispatched. Returns
    `400` if the code is wrong or TOTP is not currently enabled.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "123456"}' \\
      https://auth.example.com/auth/mfa/totp/disable
    ```
    """
    logger.info("TOTP disable request")
    user_id = await _get_current_user_id(request, db, session_service)

    success = await mfa_service.disable_totp(db, user_id, data.code)

    if not success:
        logger.warning("TOTP disable failed: invalid code for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not enabled",
        )

    tenant_id = get_current_tenant_id()
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.MFA_DISABLED,
        data={"user_id": user_id, "tenant_id": tenant_id, "method": "totp"},
    )
    await db.commit()

    logger.info("ACTION: mfa_totp_disable, user_id=%s", user_id)

    return MessageResponse(message="TOTP disabled successfully")


@router.post("/backup-codes/regenerate")
async def regenerate_backup_codes(
    request: Request,
    data: TOTPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> BackupCodesResponse:
    """Invalidate existing backup codes and issue a new set.

    Requires a valid 6-digit TOTP code (RFC 6238) as proof of possession
    before regenerating. All previously issued backup codes are immediately
    invalidated, regardless of their used/unused state, and a fresh set of
    single-use codes is returned. A `mfa.backup_codes_generated` webhook event
    with `regenerated: true` is dispatched. Returns `400` if the TOTP code is
    wrong or TOTP is not enabled.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "123456"}' \\
      https://auth.example.com/auth/mfa/backup-codes/regenerate
    ```
    """
    logger.info("Backup codes regenerate request")
    user_id = await _get_current_user_id(request, db, session_service)

    backup_codes = await mfa_service.regenerate_backup_codes(db, user_id, data.code)

    if backup_codes is None:
        logger.warning("Backup codes regenerate failed: invalid code for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not enabled",
        )

    tenant_id = get_current_tenant_id()
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.MFA_BACKUP_CODES_GENERATED,
        data={
            "user_id": user_id,
            "tenant_id": tenant_id,
            "count": len(backup_codes),
            "regenerated": True,
        },
    )
    await db.commit()

    logger.info("ACTION: mfa_backup_codes_regenerate, user_id=%s", user_id)

    return BackupCodesResponse(backup_codes=backup_codes)


@router.post("/verify", response_model=MessageResponse)
async def verify_mfa_code(
    request: Request,
    data: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> MessageResponse:
    """Verify a TOTP code or a single-use backup code during an MFA challenge.

    Accepts either a 6-digit TOTP value computed per RFC 6238 or a backup code
    in `xxxx-yyyy` format. TOTP codes have a 30-second window with ±1 step
    tolerance; backup codes are single-use and marked spent on first successful
    use. A `mfa.challenge_success` or `mfa.challenge_failed` webhook is
    dispatched accordingly. Repeated failures should be rate-limited at the
    infrastructure layer to prevent brute-force of the 6-digit space (10^6
    values). Returns `400` on any invalid code.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)

    **Authentication:** session cookie (fully authenticated user)

    **Example (TOTP):**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "123456"}' \\
      https://auth.example.com/auth/mfa/verify
    ```

    **Example (backup code):**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "a1b2-c3d4"}' \\
      https://auth.example.com/auth/mfa/verify
    ```
    """
    logger.debug("MFA code verification request")
    user_id = await _get_current_user_id(request, db, session_service)

    success = await mfa_service.verify_mfa_code(db, user_id, data.code)

    tenant_id = get_current_tenant_id()
    if not success:
        logger.warning("MFA code verification failed: invalid code for user_id=%s", user_id)
        await dispatch_webhook_event(
            db,
            tenant_id=tenant_id,
            event=WebhookEvent.MFA_CHALLENGE_FAILED,
            data={"user_id": user_id, "tenant_id": tenant_id},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code",
        )

    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.MFA_CHALLENGE_SUCCESS,
        data={"user_id": user_id, "tenant_id": tenant_id},
    )
    await db.commit()

    logger.info("ACTION: mfa_code_verify, user_id=%s", user_id)
    return MessageResponse(message="Code verified successfully")


# HTML endpoints for browser-based flow


@router.get("/setup", response_class=HTMLResponse)
async def mfa_setup_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Render the TOTP enrolment page with a QR code for authenticator apps.

    Generates a new TOTP secret (RFC 6238) and displays it as a scannable QR
    code alongside the raw Base32 secret for manual entry. If the user's
    session cookie (RFC 6265) is absent or invalid the page is rendered with
    an error and a `401` status. If TOTP is already enabled the page renders
    an informational state without overwriting the active secret; the user
    must visit the reconfigure flow to replace it.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)
    - RFC 6265 — HTTP State Management Mechanism (session cookie)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/setup
    ```
    """
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    try:
        user_id, email = await _get_current_user_email(request, db, session_service)
    except HTTPException:
        html = await branding_service.render_template(
            db,
            "auth/mfa_setup.html",
            {
                "request": request,
                "error": "Please login first",
                "qr_code": None,
                "secret": None,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_401_UNAUTHORIZED)

    # Check if already enabled
    user_mfa = await mfa_service.get_user_mfa(db, user_id)
    if user_mfa and user_mfa.totp_enabled:
        html = await branding_service.render_template(
            db,
            "auth/mfa_setup.html",
            {
                "request": request,
                "error": "TOTP is already enabled",
                "qr_code": None,
                "secret": None,
                "already_enabled": True,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    secret, uri, qr_code = await mfa_service.setup_totp(db, user_id, email)
    await db.commit()

    html = await branding_service.render_template(
        db,
        "auth/mfa_setup.html",
        {
            "request": request,
            "error": None,
            "qr_code": qr_code,
            "secret": secret,
            "already_enabled": False,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/setup/reconfigure", response_class=HTMLResponse)
async def mfa_setup_reconfigure(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Replace the active TOTP secret with a newly generated one.

    Unconditionally resets the pending TOTP secret regardless of whether TOTP
    is currently enabled, effectively starting enrolment from scratch. The new
    QR code and raw secret are rendered on the setup page so the user can
    re-scan with their authenticator app. TOTP is marked inactive until
    `POST /auth/mfa/totp/verify` is completed with a valid code from the new
    secret (RFC 6238). The previous secret and all existing backup codes are
    discarded immediately.

    **Specification:**
    - RFC 6238 — TOTP: Time-Based One-Time Password Algorithm
    - RFC 4226 — HOTP: HMAC-Based One-Time Password (underlying primitive)
    - RFC 6265 — HTTP State Management Mechanism (session cookie)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/setup/reconfigure
    ```
    """
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    try:
        user_id, email = await _get_current_user_email(request, db, session_service)
    except HTTPException:
        html = await branding_service.render_template(
            db,
            "auth/mfa_setup.html",
            {
                "request": request,
                "error": "Please login first",
                "qr_code": None,
                "secret": None,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_401_UNAUTHORIZED)

    # Generate new secret (setup_totp resets totp_enabled to False)
    secret, uri, qr_code = await mfa_service.setup_totp(db, user_id, email)
    await db.commit()

    logger.info("ACTION: mfa_reconfigure, user_id=%s", user_id)

    html = await branding_service.render_template(
        db,
        "auth/mfa_setup.html",
        {
            "request": request,
            "error": None,
            "qr_code": qr_code,
            "secret": secret,
            "already_enabled": False,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


# ===== Email MFA Endpoints =====


def _mask_email(email: str) -> str:
    """Mask an email address for display."""
    parts = email.split("@")
    if len(parts) != 2:
        return "***@***"
    local = parts[0]
    domain = parts[1]
    masked_local = local[0] + "***" if len(local) <= 2 else local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


@router.post("/email/send")
async def send_mfa_email(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    email_service: EmailService = Depends(get_email_service),
) -> EmailMFASendResponse:
    """Generate and email a time-limited OTP to the current user's primary address.

    Creates a short-lived numeric OTP, stores its hash, and dispatches a
    transactional email using the tenant-branded MJML template. The code
    expires after `settings.mfa_email_code_expiry_minutes` minutes. The
    response includes the destination address masked (e.g. `j***e@example.com`)
    so the UI can confirm delivery without exposing the full address. Returns
    `500` if code generation or email dispatch fails.

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/email/send
    ```
    """
    logger.debug("Email MFA send request")
    user_id, email = await _get_current_user_email(request, db, session_service)

    # Generate code
    code = await mfa_service.send_mfa_email_code(db, user_id, email)

    if not code:
        logger.error("Email MFA failed: could not generate code for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate MFA code",
        )

    # Send email
    subject = "Your MFA verification code"
    tenant_id = get_current_tenant_id()
    branding_service = get_branding_service()
    branding = await branding_service.get_branding(db, tenant_id=tenant_id)

    from auth.services.email_renderer import get_email_renderer

    renderer = get_email_renderer()
    body_html, body_text = await renderer.render_email_for_tenant(
        db,
        "mfa_code",
        {
            "code": code,
            "mfa_code_expiry_minutes": settings.mfa_email_code_expiry_minutes,
        },
        branding=branding,
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    sent = await email_service.send_email(email, subject, body_html, body_text)

    if not sent:
        logger.error("Email MFA failed: could not send email for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send MFA email",
        )

    await db.commit()

    logger.info("ACTION: mfa_email_send, user_id=%s", user_id)
    return EmailMFASendResponse(
        message="MFA code sent to your email",
        email_masked=_mask_email(email),
    )


@router.post("/email/verify", response_model=MessageResponse)
async def verify_mfa_email(
    request: Request,
    data: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    mfa_service: MFAService = Depends(get_mfa_service),
) -> MessageResponse:
    """Validate the email OTP submitted by the current user.

    Compares the submitted code against the hashed value stored during
    `POST /auth/mfa/email/send`. The code is single-use and expires after
    the configured window; submitting an expired or already-used code returns
    `400`. On success the code record is invalidated to prevent replay.
    Unlike TOTP, email OTP does not require RFC 6238 time-step alignment
    — validity is determined solely by expiry timestamp.

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -X POST -b session_cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"code": "847291"}' \\
      https://auth.example.com/auth/mfa/email/verify
    ```
    """
    logger.debug("Email MFA verification request")
    user_id = await _get_current_user_id(request, db, session_service)

    success = await mfa_service.verify_email_code(db, user_id, data.code)

    if not success:
        logger.warning(
            "Email MFA verification failed: invalid or expired code for user_id=%s", user_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    await db.commit()

    logger.info("ACTION: mfa_email_verify, user_id=%s", user_id)
    return MessageResponse(message="Email code verified successfully")


# HTML endpoint for email MFA


@router.get("/email", response_class=HTMLResponse)
async def mfa_email_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    branding_service: BrandingService = Depends(get_branding_service),
) -> HTMLResponse:
    """Render the email OTP verification page for browser-based MFA flows.

    Displays the email MFA challenge page pre-populated with the masked
    destination address so the user knows where to look for the code. The
    session cookie (RFC 6265) must be valid; if absent or expired the page
    renders an error with `401` status instead of redirecting, keeping the
    browser on the MFA step. Actual OTP dispatch is triggered separately via
    `POST /auth/mfa/email/send` (typically called by the page's JavaScript
    on load), and submission is handled by `POST /auth/mfa/email/verify`.

    **Specification:**
    - RFC 6265 — HTTP State Management Mechanism (session cookie)

    **Authentication:** session cookie (fully authenticated user)

    **Example:**
    ```
    curl -b session_cookies.txt \\
      https://auth.example.com/auth/mfa/email
    ```
    """
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    try:
        user_id, email = await _get_current_user_email(request, db, session_service)
    except HTTPException:
        html = await branding_service.render_template(
            db,
            "auth/mfa_email.html",
            {
                "request": request,
                "error": "Please login first",
                "email_masked": None,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_401_UNAUTHORIZED)

    html = await branding_service.render_template(
        db,
        "auth/mfa_email.html",
        {
            "request": request,
            "error": None,
            "email_masked": _mask_email(email),
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)
