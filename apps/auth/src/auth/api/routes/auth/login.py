# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Login endpoints."""

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_auth_service,
    get_branding_service,
    get_db,
    get_email_service,
    get_mfa_service,
    get_session_service,
    get_trust_service,
    get_user_service,
)
from auth.api.schemas.auth import LoginRequest, LoginResponse
from auth.config import settings
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import (
    get_csrf_cookie_name,
    get_session_cookie_domain,
    get_session_cookie_name,
    get_tenant_context,
)
from auth.services.auth import AuthService
from auth.services.branding import BrandingService
from auth.services.email import EmailService
from auth.services.mfa import MFAService
from auth.services.session import SessionService
from auth.services.trust import TrustPolicyService
from auth.services.user import UserService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter()
MFA_LOGIN_CHALLENGE_COOKIE = "mfa_login_challenge"
MFA_LOGIN_CHALLENGE_MAX_AGE = 300


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
    """Get the current tenant ID from context.

    Returns:
        The tenant ID or None if no tenant context.
    """
    tenant_ctx = get_tenant_context()
    return tenant_ctx.tenant_id if tenant_ctx else None


#: Messages shown for the ``error`` codes that other flows redirect to the login page with.
LOGIN_ERRORS = {
    "federation_failed": (
        "Sign-in with your identity provider failed. Try again or sign in with your password."
    ),
}


def _safe_next_url(next_url: str, request_host: str | None) -> str | None:
    """Return ``next_url`` when following it keeps the user on this server, else ``None``.

    A path (``/page``) is accepted, but not a protocol-relative URL (``//host``) nor any
    value holding a backslash, a tab or a line break: browsers normalise those into
    ``//host`` and follow them to another site. An absolute URL is accepted only when it
    targets the host of the request.
    """
    if not next_url or any(char in next_url for char in "\\\t\r\n"):
        return None
    if next_url.startswith("/"):
        return None if next_url.startswith("//") else next_url
    parsed = urlparse(next_url)
    if parsed.scheme in ("http", "https") and parsed.hostname == request_host:
        return next_url
    return None


def _get_client_ip(request: Request) -> str | None:
    """Get client IP address from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _set_session_cookie(response: Response, session_token: str) -> None:
    """Set session cookie on response."""
    response.set_cookie(
        key=get_session_cookie_name(),
        value=session_token,
        max_age=settings.session_expiry_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=get_session_cookie_domain(),
    )


def _get_mfa_challenge_secret() -> bytes:
    """Get signing secret for MFA login challenge cookies."""
    if settings.jwks_encryption_key:
        return settings.jwks_encryption_key.encode("utf-8")
    # Dev/test fallback to keep feature functional without extra config.
    return (settings.database_url + settings.session_cookie_name).encode("utf-8")


def _create_mfa_login_challenge(
    user_id: str,
    email: str,
    next_url: str,
    tenant_id: str | None,
) -> str:
    payload = {
        "uid": user_id,
        "email": email,
        "next": next_url,
        "tenant_id": tenant_id,
        "exp": int(time.time()) + MFA_LOGIN_CHALLENGE_MAX_AGE,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_get_mfa_challenge_secret(), body.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{body}.{signature}"


def _parse_mfa_login_challenge(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected_sig = hmac.new(
        _get_mfa_challenge_secret(), body.encode("ascii"), hashlib.sha256
    ).digest()
    expected_signature = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")
    if not hmac.compare_digest(signature, expected_signature):
        return None
    try:
        padded = body + "=" * ((4 - len(body) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def _set_mfa_challenge_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=MFA_LOGIN_CHALLENGE_COOKIE,
        value=token,
        max_age=MFA_LOGIN_CHALLENGE_MAX_AGE,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=get_session_cookie_domain(),
    )


def _clear_mfa_challenge_cookie(response: Response) -> None:
    response.delete_cookie(
        key=MFA_LOGIN_CHALLENGE_COOKIE,
        path="/",
        domain=get_session_cookie_domain(),
    )


def _mask_email(email: str) -> str:
    parts = email.split("@")
    if len(parts) != 2:
        return "***@***"
    local, domain = parts
    masked_local = local[:1] + "***" if len(local) <= 2 else local[:1] + "***" + local[-1:]
    return f"{masked_local}@{domain}"


async def _build_mfa_email(
    db: AsyncSession, code: str, branding_service: BrandingService, tenant_id=None
) -> tuple[str, str]:
    branding = await branding_service.get_branding(db, tenant_id=tenant_id)

    from auth.services.email_renderer import get_email_renderer

    renderer = get_email_renderer()
    return await renderer.render_email_for_tenant(
        db,
        "mfa_code",
        {
            "code": code,
            "mfa_code_expiry_minutes": settings.mfa_email_code_expiry_minutes,
        },
        branding=branding,
        tenant_id=str(tenant_id) if tenant_id else None,
    )


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
    branding_service: BrandingService = Depends(get_branding_service),
    verified: str = "",
    reset: str = "",
    registered: str = "",
    error: str = "",
    next: str = "",
    email: str = "",
) -> HTMLResponse | RedirectResponse:
    """Render the HTML login form for password-based authentication.

    Serves the Jinja2-rendered login page at `GET /auth/login`. If the
    request already carries a valid session cookie the handler short-circuits
    and issues a `302` redirect to `?next=` (if it starts with `/`) or to
    `/auth/settings`, so authenticated users are never shown the form again.
    Query parameters `verified`, `reset`, and `registered` inject a one-time
    success banner (e.g. after email verification or password reset); `error`
    shows the message of a known failure code such as `federation_failed`. This
    endpoint is the user-facing entry point for the OAuth2 authorization-code
    flow (RFC 6749 §4.1) when an authorization request redirects the resource
    owner here for authentication.

    **Specification:** RFC 6265 §4 (HTTP State Management — session cookie
    read); RFC 6749 §4.1 (Authorization Code Grant — resource owner
    authentication step).

    **Authentication:** none (renders login form; redirects to settings if
    already authenticated via session cookie).

    **Example:**
    ```
    curl https://auth.example.com/auth/login
    ```

    With post-verification banner and a continuation target:
    ```
    curl "https://auth.example.com/auth/login?verified=1&next=/oauth2/authorize%3Fclient_id%3Dabc"
    ```
    """
    logger.debug("Login form requested, next=%s", next)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Check if user is already authenticated
    session_token = request.cookies.get(get_session_cookie_name())
    if session_token:
        user = await session_service.get_user_by_session_token(db, session_token)
        if user:
            # User is already logged in, redirect to next or settings
            redirect_url = _safe_next_url(next, request.url.hostname) or (
                f"{tenant_prefix}/auth/settings"
            )
            logger.debug("User already authenticated, redirecting to %s", redirect_url)
            return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    success = None
    if verified == "1":
        success = "Email verified successfully. You can now log in."
    elif reset == "1":
        success = "Password reset successfully. You can now log in."
    elif registered == "1":
        success = "Registration successful. Please check your email to verify your account."

    html = await branding_service.render_template(
        db,
        "auth/login.html",
        {
            "request": request,
            "error": LOGIN_ERRORS.get(error),
            "success": success,
            "email": email,
            "mfa_required": False,
            "next": next,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/login", response_class=HTMLResponse, response_model=None)
async def login_submit(
    request: Request,
    email: str | None = Form(None),
    password: str | None = Form(None),
    otp: str | None = Form(None),
    next: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    session_service: SessionService = Depends(get_session_service),
    branding_service: BrandingService = Depends(get_branding_service),
    trust_service: TrustPolicyService = Depends(get_trust_service),
    email_service: EmailService = Depends(get_email_service),
    send_email_code: str | None = Form(None),
    user_service: UserService = Depends(get_user_service),
) -> HTMLResponse | RedirectResponse:
    """Process the HTML login form submission and establish a session cookie.

    Implements a two-step authentication flow. Step 1: validates `email` +
    `password` credentials; on success the handler checks whether the account
    has TOTP MFA enabled. If MFA is active a short-lived, HMAC-signed
    `mfa_login_challenge` cookie (TTL 300 s) is set and the form is
    re-rendered asking for the OTP — no session is created yet. Step 2:
    triggered when the POST includes an `otp` value or `send_email_code=1`
    against an existing challenge cookie; on successful OTP/email-code
    verification the handler creates the session. On final success a `303 See
    Other` redirect is issued to `?next=` (relative URLs only; absolute URLs
    are validated against `request.url.hostname` to prevent open-redirect
    per RFC 6749 §10.15). The session cookie (`HttpOnly; SameSite=lax`) is
    set on the redirect response (RFC 6265 §4.1). A separate JS-readable
    CSRF cookie is also written. Invalid credentials re-render the form with
    `401`; trust-policy violations return `403`.

    **Specification:** RFC 6265 §4.1 (HTTP State Management — session cookie
    write); RFC 6749 §4.1 (Authorization Code Grant — resource owner
    authentication step); RFC 6749 §10.15 (Open Redirect mitigation).

    **Authentication:** form credentials (`email` + `password`); optional
    `otp` for MFA step 2. Establishes `HttpOnly` session cookie on success.

    **Example — password-only login (captures session cookie):**
    ```
    curl -X POST -c cookies.txt \\
      -d "email=user@example.com" \\
      -d "password=S3cret!" \\
      -d "csrf_token=<token>" \\
      https://auth.example.com/auth/login -L
    ```

    **Example — MFA step 2 (OTP submission):**
    ```
    curl -X POST -b cookies.txt -c cookies.txt \\
      -d "otp=123456" \\
      -d "csrf_token=<token>" \\
      https://auth.example.com/auth/login -L
    ```
    """
    logger.info("Login attempt for email=%s", email)
    logger.debug(
        "Login form submitted: email=%s, next=%s, ip=%s", email, next, _get_client_ip(request)
    )

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    otp_code = otp.strip() if otp else ""
    challenge_payload = _parse_mfa_login_challenge(request.cookies.get(MFA_LOGIN_CHALLENGE_COOKIE))
    send_email_raw = send_email_code if isinstance(send_email_code, str) else ""
    send_email_requested = send_email_raw.strip().lower() in {"1", "true", "on", "yes"}

    user = None
    if otp_code or (challenge_payload and send_email_requested):
        if not challenge_payload:
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": email or "",
                    "error": "MFA session expired. Please sign in again.",
                    "success": None,
                    "mfa_required": False,
                    "next": next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            response = HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)
            _clear_mfa_challenge_cookie(response)
            return response

        challenge_user_id = challenge_payload["uid"]
        challenge_email = challenge_payload.get("email", "")
        challenge_next = challenge_payload.get("next", "") or next
        if email:
            email = email.strip()
        if email and challenge_email and email.lower() != challenge_email.lower():
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": challenge_email,
                    "error": "MFA challenge mismatch. Please sign in again.",
                    "success": None,
                    "mfa_required": False,
                    "next": challenge_next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            response = HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)
            _clear_mfa_challenge_cookie(response)
            return response

        user = await user_service.get_by_id(db, uuid.UUID(str(challenge_user_id)))
        if not user:
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": challenge_email,
                    "error": "User not found. Please sign in again.",
                    "success": None,
                    "mfa_required": False,
                    "next": challenge_next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            response = HTMLResponse(content=html, status_code=status.HTTP_401_UNAUTHORIZED)
            _clear_mfa_challenge_cookie(response)
            return response

        if send_email_requested:
            user_email = await auth_service.get_user_primary_email(db, str(user.id))
            target_email = user_email or challenge_email
            if not target_email:
                html = await branding_service.render_template(
                    db,
                    "auth/login.html",
                    {
                        "request": request,
                        "email": challenge_email,
                        "error": "No email available for this account.",
                        "success": None,
                        "mfa_required": True,
                        "next": challenge_next,
                        "tenant_prefix": tenant_prefix,
                    },
                    tenant_id=tenant_id,
                )
                return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

            code = await mfa_service.send_mfa_email_code(db, str(user.id), target_email)
            if not code:
                html = await branding_service.render_template(
                    db,
                    "auth/login.html",
                    {
                        "request": request,
                        "email": challenge_email,
                        "error": "Failed to generate email MFA code.",
                        "success": None,
                        "mfa_required": True,
                        "next": challenge_next,
                        "tenant_prefix": tenant_prefix,
                    },
                    tenant_id=tenant_id,
                )
                return HTMLResponse(content=html, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

            mfa_html, mfa_text = await _build_mfa_email(db, code, branding_service, tenant_id)
            sent = await email_service.send_email(
                target_email,
                "Your MFA verification code",
                mfa_html,
                mfa_text,
            )
            if not sent:
                await db.rollback()
                html = await branding_service.render_template(
                    db,
                    "auth/login.html",
                    {
                        "request": request,
                        "email": challenge_email,
                        "error": "Failed to send MFA email. Please try again.",
                        "success": None,
                        "mfa_required": True,
                        "next": challenge_next,
                        "tenant_prefix": tenant_prefix,
                    },
                    tenant_id=tenant_id,
                )
                return HTMLResponse(content=html, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

            await db.commit()
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": challenge_email,
                    "error": None,
                    "success": f"Verification code sent to {_mask_email(target_email)}",
                    "mfa_required": True,
                    "next": challenge_next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_200_OK)

        # Unreachable today: reaching here means send_email_code was not
        # requested, which the branch condition above only allows when an OTP
        # was submitted. Kept as a guard in case that condition is relaxed.
        if not otp_code:  # pragma: no cover
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": challenge_email,
                    "error": "Enter your authenticator or email code.",
                    "success": None,
                    "mfa_required": True,
                    "next": challenge_next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

        if not await mfa_service.verify_mfa_code_with_email(db, str(user.id), otp_code):
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": challenge_email,
                    "error": "Invalid verification code.",
                    "success": None,
                    "mfa_required": True,
                    "next": challenge_next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

        email = challenge_email
        next = challenge_next
    else:
        # Step 1: password authentication
        email = (email or "").strip()
        if not email or not password:
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": email,
                    "error": "Email and password are required",
                    "success": None,
                    "mfa_required": False,
                    "next": next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

        user = await auth_service.authenticate(db, email, password)

        if not user:
            logger.warning("Login failed: invalid credentials for email=%s", email)
            await dispatch_webhook_event(
                db,
                tenant_id=tenant_id,
                event=WebhookEvent.LOGIN_FAILED,
                data={
                    "email": email,
                    "reason": "invalid_credentials",
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "ip_address": _get_client_ip(request),
                },
            )
            await db.commit()

            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": email,
                    "error": "Invalid email or password",
                    "success": None,
                    "mfa_required": False,
                    "next": next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_401_UNAUTHORIZED)

        logger.debug("User authenticated: user_id=%s, email=%s", user.id, email)

        # If MFA enabled, switch to step 2 with a temporary challenge cookie.
        user_mfa = await mfa_service.get_user_mfa(db, str(user.id))
        if user_mfa and user_mfa.totp_enabled:
            challenge = _create_mfa_login_challenge(
                user_id=str(user.id),
                email=email,
                next_url=next,
                tenant_id=str(tenant_id) if tenant_id else None,
            )
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": email,
                    "error": None,
                    "success": "Password verified. Enter your authenticator code to continue.",
                    "mfa_required": True,
                    "next": next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            response = HTMLResponse(content=html, status_code=status.HTTP_200_OK)
            _set_mfa_challenge_cookie(response, challenge)
            return response

    # Check tenant trust policy
    if tenant_id:
        allowed, trust_error = await trust_service.can_user_access_tenant(db, user, tenant_id)
        if not allowed:
            logger.warning(
                "Login denied by trust policy: user=%s tenant=%s reason=%s",
                user.id,
                tenant_id,
                trust_error,
            )
            html = await branding_service.render_template(
                db,
                "auth/login.html",
                {
                    "request": request,
                    "email": email,
                    "error": trust_error or "Access denied",
                    "success": None,
                    "mfa_required": False,
                    "next": next,
                    "tenant_prefix": tenant_prefix,
                },
                tenant_id=tenant_id,
            )
            return HTMLResponse(content=html, status_code=status.HTTP_403_FORBIDDEN)

    # Create session
    session_token, csrf_token = await session_service.create_session(
        db,
        str(user.id),
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    login_data = {
        "user_id": str(user.id),
        "email": email,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "ip_address": _get_client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.LOGIN_SUCCESS,
        data=login_data,
    )
    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.SESSION_CREATED,
        data=login_data,
    )

    await db.commit()

    # Determine redirect URL (use next if provided and safe, otherwise /auth/settings)
    redirect_url = _safe_next_url(next, request.url.hostname) or f"{tenant_prefix}/auth/settings"

    logger.info("ACTION: user_login, user_id=%s, email=%s", user.id, email)

    # Redirect to next URL or home with session cookie
    redirect_response = RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _set_session_cookie(redirect_response, session_token)
    _clear_mfa_challenge_cookie(redirect_response)

    # Store CSRF token in a separate cookie (readable by JS for AJAX requests)
    redirect_response.set_cookie(
        key=get_csrf_cookie_name(),
        value=csrf_token,
        max_age=settings.session_expiry_days * 24 * 60 * 60,
        httponly=False,  # JS needs to read this for AJAX
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=get_session_cookie_domain(),
    )

    return redirect_response


@router.post("/login/api")
async def login_api(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    mfa_service: MFAService = Depends(get_mfa_service),
    session_service: SessionService = Depends(get_session_service),
    trust_service: TrustPolicyService = Depends(get_trust_service),
) -> Response:
    """Authenticate via JSON and establish a session cookie (API variant).

    Accepts a JSON body with `email`, `password`, and an optional `otp` field.
    Unlike the HTML form flow this endpoint handles both password validation
    and MFA verification in a single request: if the account has TOTP enabled
    and `otp` is absent the handler returns `403 MFA required`; if `otp` is
    present it is verified before the session is created. On success the
    response body contains `{"message": "Login successful", "csrf_token":
    "<token>"}` and an `HttpOnly; SameSite=lax` session cookie is set
    (RFC 6265 §4.1). Tenant trust-policy violations return `403`. This
    endpoint is suitable for programmatic / SPA clients that cannot follow
    the multi-step HTML form redirect flow.

    **Specification:** RFC 6265 §4.1 (HTTP State Management — session cookie
    write); RFC 6749 §4.1 (Authorization Code Grant — resource owner
    authentication step).

    **Authentication:** JSON credentials (`email` + `password`; `otp` when
    MFA is active). Establishes `HttpOnly` session cookie on success.

    **Responses:**
    - `200` — session created; session cookie + CSRF token returned
    - `401` — invalid email or password
    - `403` — MFA required (no OTP supplied), invalid OTP, or trust-policy denial

    **Example — password + TOTP login:**
    ```
    curl -X POST -c cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"email": "user@example.com", "password": "S3cret!", "otp": "123456"}' \\
      https://auth.example.com/auth/login/api
    ```

    **Example — password only (account without MFA):**
    ```
    curl -X POST -c cookies.txt \\
      -H "Content-Type: application/json" \\
      -d '{"email": "user@example.com", "password": "S3cret!"}' \\
      https://auth.example.com/auth/login/api
    ```
    """
    logger.info("API login attempt for email=%s", data.email)
    logger.debug("API login request: email=%s, ip=%s", data.email, _get_client_ip(request))

    tenant_id = get_current_tenant_id()

    # Authenticate user
    user = await auth_service.authenticate(db, data.email, data.password)

    if not user:
        logger.warning("API login failed: invalid credentials for email=%s", data.email)
        await dispatch_webhook_event(
            db,
            tenant_id=tenant_id,
            event=WebhookEvent.LOGIN_FAILED,
            data={
                "email": data.email,
                "reason": "invalid_credentials",
                "tenant_id": str(tenant_id) if tenant_id else None,
                "ip_address": _get_client_ip(request),
            },
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.debug("API user authenticated: user_id=%s, email=%s", user.id, data.email)

    user_mfa = await mfa_service.get_user_mfa(db, str(user.id))
    if user_mfa and user_mfa.totp_enabled:
        otp_code = data.otp.strip() if data.otp else ""
        if not otp_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA required",
            )
        if not await mfa_service.verify_mfa_code_with_email(db, str(user.id), otp_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid verification code",
            )

    # Check tenant trust policy
    if tenant_id:
        allowed, trust_error = await trust_service.can_user_access_tenant(db, user, tenant_id)
        if not allowed:
            logger.warning(
                "API login denied by trust policy: user=%s tenant=%s reason=%s",
                user.id,
                tenant_id,
                trust_error,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=trust_error or "Access denied",
            )

    # Create session
    session_token, csrf_token = await session_service.create_session(
        db,
        str(user.id),
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    login_data = {
        "user_id": str(user.id),
        "email": data.email,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "ip_address": _get_client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.LOGIN_SUCCESS, data=login_data
    )
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.SESSION_CREATED, data=login_data
    )

    await db.commit()

    logger.info("ACTION: user_login_api, user_id=%s, email=%s", user.id, data.email)

    # Return response with session cookie
    response = Response(
        content=LoginResponse(
            message="Login successful",
            csrf_token=csrf_token,
        ).model_dump_json(),
        media_type="application/json",
    )
    _set_session_cookie(response, session_token)

    return response
