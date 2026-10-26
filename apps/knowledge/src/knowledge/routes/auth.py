# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 authentication routes for web UI."""

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import (
    ACCESS_TOKEN_COOKIE,
    ACTIVE_TENANT_COOKIE,
    REFRESH_TOKEN_COOKIE,
    USER_INFO_COOKIE,
    get_web_auth_context,
)
from knowledge.auth.models import User, WebAuthContext
from knowledge.config import TEMPLATES_DIR, docs_context, get_settings
from knowledge.database import get_db
from knowledge.models import PlanType, Tenant, TenantMember, TenantMemberRole
from knowledge.services.auth_api import AuthAPIClient, AuthAPIError, get_auth_api_client

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[docs_context])
MFA_SIGNIN_CHALLENGE_COOKIE = "knowledge_mfa_signin_challenge"
MFA_SIGNIN_CHALLENGE_MAX_AGE = 300


def _generate_pkce_verifier() -> str:
    """Generate a PKCE code verifier."""
    return secrets.token_urlsafe(64)


def _generate_pkce_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _get_cookie_settings() -> dict:
    """Get common cookie settings."""
    return {
        "path": "/",
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain or None,
    }


def _get_mfa_signing_secret() -> bytes:
    """Secret used to sign MFA signin challenge cookies."""
    if settings.oauth2_client_secret:
        return settings.oauth2_client_secret.encode("utf-8")
    return (settings.database_url + settings.oauth2_client_id).encode("utf-8")


def _create_mfa_signin_challenge(
    email: str,
    password: str,
    redirect: str | None,
    plan_type: str | None,
    company_name: str | None,
    company_size: str | None,
    workspace_name: str | None,
    remember: bool,
) -> str:
    payload = {
        "email": email,
        "password": password,
        "redirect": redirect,
        "plan_type": plan_type,
        "company_name": company_name,
        "company_size": company_size,
        "workspace_name": workspace_name,
        "remember": remember,
        "exp": int(time.time()) + MFA_SIGNIN_CHALLENGE_MAX_AGE,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_get_mfa_signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    return f"{body}.{signature}"


def _parse_mfa_signin_challenge(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(_get_mfa_signing_secret(), body.encode("ascii"), hashlib.sha256).digest()
    expected_signature = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
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


def _set_mfa_signin_challenge_cookie(response: Response, token: str) -> None:
    cookie_settings = _get_cookie_settings()
    response.set_cookie(
        MFA_SIGNIN_CHALLENGE_COOKIE,
        token,
        max_age=MFA_SIGNIN_CHALLENGE_MAX_AGE,
        **cookie_settings,
    )


def _clear_mfa_signin_challenge_cookie(response: Response) -> None:
    delete_settings: dict[str, Any] = {"path": "/"}
    if settings.cookie_domain:
        delete_settings["domain"] = settings.cookie_domain
    response.delete_cookie(MFA_SIGNIN_CHALLENGE_COOKIE, **delete_settings)


@router.get("/login")
async def login(
    request: Request,
    redirect: str = Query(default="/dashboard"),
):
    """Redirect to OAuth2 authorization endpoint with PKCE."""
    if not settings.oauth2_issuer or not settings.oauth2_frontend_client_id:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "Configuration Error",
                "error_description": "OAuth2 is not configured. Please set OAUTH2_ISSUER and OAUTH2_FRONTEND_CLIENT_ID.",
            },
            status_code=500,
        )

    # Generate PKCE values
    state = secrets.token_urlsafe(32)
    code_verifier = _generate_pkce_verifier()
    code_challenge = _generate_pkce_challenge(code_verifier)

    # Build redirect URI
    if settings.app_base_url:
        redirect_uri = f"{settings.app_base_url}/auth/callback"
    else:
        redirect_uri = str(request.url_for("callback"))

    # Build authorization URL
    params = {
        "client_id": settings.oauth2_frontend_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid profile email offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"{settings.oauth2_issuer}/oauth2/authorize?{urlencode(params)}"

    response = RedirectResponse(url=auth_url, status_code=302)

    # Store state and verifier in cookies
    cookie_settings = _get_cookie_settings()
    cookie_settings["max_age"] = 600  # 10 minutes

    response.set_cookie("oauth_state", state, **cookie_settings)
    response.set_cookie("oauth_redirect", redirect, **cookie_settings)
    response.set_cookie("oauth_code_verifier", code_verifier, **cookie_settings)

    return response


@router.get("/callback", response_class=HTMLResponse)
async def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    oauth_state: str | None = Cookie(default=None),
    oauth_redirect: str | None = Cookie(default=None),
    oauth_code_verifier: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 callback - exchange code for tokens."""
    # Handle OAuth error
    if error:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": error,
                "error_description": error_description or "Authentication failed",
            },
            status_code=400,
        )

    # Verify state
    if not state or state != oauth_state:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "Invalid State",
                "error_description": "The state parameter does not match. This may be a CSRF attack.",
            },
            status_code=400,
        )

    if not code:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "Missing Code",
                "error_description": "No authorization code received.",
            },
            status_code=400,
        )

    if not oauth_code_verifier:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "Missing Verifier",
                "error_description": "PKCE code verifier not found.",
            },
            status_code=400,
        )

    # Build redirect URI
    if settings.app_base_url:
        redirect_uri = f"{settings.app_base_url}/auth/callback"
    else:
        redirect_uri = str(request.url_for("callback"))

    # Exchange code for tokens
    token_url = f"{settings.oauth2_issuer}/oauth2/token"

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.oauth2_frontend_client_id,
                    "code_verifier": oauth_code_verifier,
                },
            )

            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: {token_response.text}")
                return templates.TemplateResponse(
                    request,
                    "auth/error.html",
                    {
                        "error": "Token Exchange Failed",
                        "error_description": "Failed to exchange authorization code for tokens.",
                    },
                    status_code=400,
                )

            tokens = token_response.json()

    except Exception as e:
        logger.error(f"Token exchange error: {e}")
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "Connection Error",
                "error_description": f"Failed to connect to authentication server: {e}",
            },
            status_code=500,
        )

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)
    if not access_token:
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {
                "error": "No Access Token",
                "error_description": "No access token in response.",
            },
            status_code=400,
        )

    # Get user info from userinfo endpoint (contains name, email, nickname)
    user_claims = _decode_jwt_payload(access_token)  # For sub and scope

    try:
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                f"{settings.oauth2_issuer}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code == 200:
                userinfo = userinfo_response.json()
                # Merge userinfo claims into user_claims
                user_claims.update(userinfo)
    except Exception as e:
        logger.warning(f"Failed to fetch userinfo: {e}")

    user = User.from_jwt_claims(user_claims)

    # Check if user has any tenants, create personal tenant if not
    result = await db.execute(select(TenantMember).where(TenantMember.user_id == user.id).limit(1))
    membership = result.scalar_one_or_none()

    active_tenant_id = None

    if not membership:
        # Create personal tenant (prefer nickname over full name)
        tenant_name = user.display_name or user.email or f"User {str(user.id)[:8]}"
        tenant_slug = f"personal-{str(user.id)[:8]}"

        tenant = Tenant(
            name=f"{tenant_name}'s Workspace",
            slug=tenant_slug,
            plan=PlanType.FREE,
            settings={},
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        # Create owner membership
        membership = TenantMember(
            organization_id=tenant.id,
            user_id=user.id,
            role=TenantMemberRole.OWNER,
            display_name=user.display_name,
            email=user.email,
        )
        db.add(membership)
        await db.commit()

        active_tenant_id = str(tenant.id)
        logger.info(f"Created personal tenant for user {user.id}: {tenant_slug}")
    else:
        active_tenant_id = str(membership.organization_id)
        # Update cached user info on login
        membership.display_name = user.display_name
        membership.email = user.email
        await db.commit()

    # Build redirect URL
    redirect_url = oauth_redirect or "/dashboard"

    # Create response with cookies
    response = RedirectResponse(url=redirect_url, status_code=302)
    cookie_settings = _get_cookie_settings()

    # Set auth cookies
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=expires_in,
        **cookie_settings,
    )

    if refresh_token:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE,
            refresh_token,
            max_age=30 * 24 * 3600,  # 30 days
            **cookie_settings,
        )

    # Set active tenant cookie
    response.set_cookie(
        ACTIVE_TENANT_COOKIE,
        active_tenant_id,
        max_age=365 * 24 * 3600,  # 1 year
        **cookie_settings,
    )

    # Set user info cookie (readable by JS)
    user_info = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
    }
    response.set_cookie(
        USER_INFO_COOKIE,
        json.dumps(user_info),
        max_age=expires_in,
        httponly=False,  # Allow JS access
        secure=settings.cookie_secure,
        samesite="lax",
    )

    # Clear OAuth state cookies
    response.delete_cookie("oauth_state")
    response.delete_cookie("oauth_redirect")
    response.delete_cookie("oauth_code_verifier")

    return response


@router.get("/logout")
async def logout(
    request: Request,
    redirect: str = Query(default="/"),
):
    """Log out by clearing cookies."""
    response = RedirectResponse(url=redirect, status_code=302)

    # Cookie delete settings must match creation settings
    delete_settings: dict[str, Any] = {
        "path": "/",
        "secure": settings.cookie_secure,
        "samesite": "lax",
    }
    if settings.cookie_domain:
        delete_settings["domain"] = settings.cookie_domain

    # Clear all auth cookies
    response.delete_cookie(ACCESS_TOKEN_COOKIE, **delete_settings)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, **delete_settings)
    response.delete_cookie(ACTIVE_TENANT_COOKIE, **delete_settings)
    response.delete_cookie(USER_INFO_COOKIE, path="/", samesite="lax")

    return response


@router.post("/refresh")
async def refresh_token(
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_TOKEN_COOKIE),
):
    """Refresh the access token."""
    if not refresh_token:
        return RedirectResponse(url="/auth/login", status_code=302)

    token_url = f"{settings.oauth2_issuer}/oauth2/token"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.oauth2_frontend_client_id,
                },
            )

            if response.status_code != 200:
                # Refresh failed, redirect to login
                return RedirectResponse(url="/auth/login", status_code=302)

            tokens = response.json()

    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return RedirectResponse(url="/auth/login", status_code=302)

    access_token = tokens.get("access_token")
    new_refresh_token = tokens.get("refresh_token", refresh_token)
    expires_in = tokens.get("expires_in", 3600)

    if not access_token:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Redirect back to referrer or dashboard
    redirect_url = request.headers.get("Referer", "/dashboard")
    redirect_response = RedirectResponse(url=redirect_url, status_code=302)
    cookie_settings = _get_cookie_settings()

    redirect_response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=expires_in,
        **cookie_settings,
    )

    if new_refresh_token:
        redirect_response.set_cookie(
            REFRESH_TOKEN_COOKIE,
            new_refresh_token,
            max_age=30 * 24 * 3600,
            **cookie_settings,
        )

    return redirect_response


def _decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification (for extracting claims).

    This is safe because we already validated the token with the auth server.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}

        # Add padding if needed
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


# =============================================================================
# Signup / Signin / Verify routes (integrated auth)
# =============================================================================


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(
    request: Request,
    redirect: str | None = Query(None),
):
    """Display signup form."""
    return templates.TemplateResponse(
        request,
        "auth/signup.html",
        {"error": None, "email": None, "redirect": redirect},
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    nickname: str = Form(...),
    firstname: str = Form(...),
    lastname: str = Form(...),
    workspace_name: str = Form(...),
    plan_type: str = Form("personal"),
    company_name: str | None = Form(None),
    company_size: str | None = Form(None),
    redirect: str | None = Form(None),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Process signup form submission."""
    # Validate password confirmation
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {
                "error": "Passwords do not match",
                "email": email,
                "nickname": nickname,
                "firstname": firstname,
                "lastname": lastname,
                "workspace_name": workspace_name,
                "plan_type": plan_type,
                "company_name": company_name,
                "redirect": redirect,
            },
            status_code=400,
        )

    # Validate enterprise plan requirements
    if plan_type == "enterprise" and not company_name:
        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {
                "error": "Company name is required for enterprise plans",
                "email": email,
                "nickname": nickname,
                "firstname": firstname,
                "lastname": lastname,
                "workspace_name": workspace_name,
                "plan_type": plan_type,
                "redirect": redirect,
            },
            status_code=400,
        )

    # Register user via Auth API
    try:
        result = await auth_client.register(
            email, password, nickname=nickname, firstname=firstname, lastname=lastname
        )
        logger.info("User registered: user_id=%s, email=%s", result.user_id, email)
    except AuthAPIError as e:
        # If email already exists, redirect to signin so the user can log in
        # and a new workspace will be created automatically
        if "already registered" in e.message.lower():
            params = {
                "email": email,
                "workspace_name": workspace_name,
                "success": "You already have an account. Sign in to create a new workspace.",
            }
            if redirect:
                params["redirect"] = redirect
            if plan_type == "enterprise":
                params["plan_type"] = plan_type
                if company_name:  # pragma: no branch – guarded by L513
                    params["company_name"] = company_name
                if company_size:
                    params["company_size"] = company_size
            return RedirectResponse(
                url=f"/auth/signin?{urlencode(params)}",
                status_code=303,
            )

        return templates.TemplateResponse(
            request,
            "auth/signup.html",
            {
                "error": e.message,
                "email": email,
                "nickname": nickname,
                "firstname": firstname,
                "lastname": lastname,
                "workspace_name": workspace_name,
                "plan_type": plan_type,
                "company_name": company_name,
                "redirect": redirect,
            },
            status_code=400,
        )

    # Redirect to verify page with workspace name and plan info
    params = {"email": email, "workspace_name": workspace_name}
    if redirect:
        params["redirect"] = redirect
    if plan_type == "enterprise":
        params["plan_type"] = plan_type
        if company_name:  # pragma: no branch – guarded by L513
            params["company_name"] = company_name
        if company_size:
            params["company_size"] = company_size

    return RedirectResponse(
        url=f"/auth/verify?{urlencode(params)}",
        status_code=303,
    )


@router.get("/verify", response_class=HTMLResponse)
async def verify_form(
    request: Request,
    email: str = Query(...),
    workspace_name: str | None = Query(None),
    plan_type: str | None = Query(None),
    company_name: str | None = Query(None),
    company_size: str | None = Query(None),
    redirect: str | None = Query(None),
):
    """Display email verification form."""
    return templates.TemplateResponse(
        request,
        "auth/verify.html",
        {
            "email": email,
            "workspace_name": workspace_name,
            "plan_type": plan_type,
            "company_name": company_name,
            "company_size": company_size,
            "redirect": redirect,
            "error": None,
            "success": None,
        },
    )


@router.post("/verify", response_class=HTMLResponse)
async def verify_submit(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    workspace_name: str | None = Form(None),
    plan_type: str | None = Form(None),
    company_name: str | None = Form(None),
    company_size: str | None = Form(None),
    redirect: str | None = Form(None),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Process email verification."""
    try:
        await auth_client.verify_email(email, code)
        logger.info("Email verified: email=%s", email)
    except AuthAPIError as e:
        return templates.TemplateResponse(
            request,
            "auth/verify.html",
            {
                "email": email,
                "workspace_name": workspace_name,
                "plan_type": plan_type,
                "company_name": company_name,
                "company_size": company_size,
                "redirect": redirect,
                "error": e.message,
                "success": None,
            },
            status_code=400,
        )

    # Store workspace name and plan info for use after signin
    params = {"verified": "1"}
    if workspace_name:
        params["workspace_name"] = workspace_name
    if redirect:
        params["redirect"] = redirect
    if plan_type == "enterprise":
        params["plan_type"] = plan_type
        if company_name:
            params["company_name"] = company_name
        if company_size:
            params["company_size"] = company_size

    return RedirectResponse(
        url=f"/auth/signin?{urlencode(params)}",
        status_code=303,
    )


@router.post("/verify/resend", response_class=HTMLResponse)
async def verify_resend(
    request: Request,
    email: str = Form(...),
    workspace_name: str | None = Form(None),
    plan_type: str | None = Form(None),
    company_name: str | None = Form(None),
    company_size: str | None = Form(None),
    redirect: str | None = Form(None),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Resend verification email."""
    with contextlib.suppress(AuthAPIError):
        await auth_client.resend_verification(email)

    return templates.TemplateResponse(
        request,
        "auth/verify.html",
        {
            "email": email,
            "workspace_name": workspace_name,
            "plan_type": plan_type,
            "company_name": company_name,
            "company_size": company_size,
            "redirect": redirect,
            "error": None,
            "success": "If an account exists with this email, a verification code has been sent.",
        },
    )


@router.get("/signin", response_class=HTMLResponse)
async def signin_form(
    request: Request,
    verified: str | None = Query(None),
    reset: str | None = Query(None),
    success: str | None = Query(None),
    email: str | None = Query(None),
    redirect: str | None = Query(None),
    plan_type: str | None = Query(None),
    company_name: str | None = Query(None),
    company_size: str | None = Query(None),
    workspace_name: str | None = Query(None),
    mfa_required: str | None = Query(None),
):
    """Display signin form."""
    # Determine success message
    if not success and reset == "1":
        success = "Password reset successfully! You can now sign in."

    return templates.TemplateResponse(
        request,
        "auth/signin.html",
        {
            "error": None,
            "success": success,
            "verified": verified == "1",
            "email": email,
            "password": None,
            "redirect": redirect,
            "plan_type": plan_type,
            "company_name": company_name,
            "company_size": company_size,
            "workspace_name": workspace_name,
            "mfa_required": mfa_required == "1",
            "remember": False,
        },
    )


@router.post("/signin", response_class=HTMLResponse)
async def signin_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    otp: str | None = Form(None),
    send_email_code: str | None = Form(None),
    redirect: str | None = Form(None),
    plan_type: str | None = Form(None),
    company_name: str | None = Form(None),
    company_size: str | None = Form(None),
    workspace_name: str | None = Form(None),
    remember: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Process signin form submission (ROPC grant)."""
    email = email.strip()
    password = password or ""
    otp = otp.strip() if otp else None
    challenge = _parse_mfa_signin_challenge(request.cookies.get(MFA_SIGNIN_CHALLENGE_COOKIE))
    send_email_raw = send_email_code if isinstance(send_email_code, str) else ""
    send_email_requested = send_email_raw.strip().lower() in {"1", "true", "on", "yes"}

    if (
        challenge
        and not password
        and email
        and email.lower() == str(challenge.get("email", "")).lower()
    ):
        password = str(challenge.get("password") or "")
        redirect = redirect or challenge.get("redirect")
        plan_type = plan_type or challenge.get("plan_type")
        company_name = company_name or challenge.get("company_name")
        company_size = company_size or challenge.get("company_size")
        workspace_name = workspace_name or challenge.get("workspace_name")
        remember = remember or ("1" if challenge.get("remember") else None)

    if otp and not password:
        response: Response
        response = templates.TemplateResponse(
            request,
            "auth/signin.html",
            {
                "error": "MFA session expired. Enter email and password again.",
                "success": None,
                "verified": False,
                "email": email,
                "password": None,
                "redirect": redirect,
                "plan_type": plan_type,
                "company_name": company_name,
                "company_size": company_size,
                "workspace_name": workspace_name,
                "mfa_required": False,
                "remember": remember is not None,
            },
            status_code=400,
        )
        _clear_mfa_signin_challenge_cookie(response)
        return response

    if send_email_requested:
        if not email or not password:
            response = templates.TemplateResponse(
                request,
                "auth/signin.html",
                {
                    "error": "MFA session expired. Enter email and password again.",
                    "success": None,
                    "verified": False,
                    "email": email,
                    "password": None,
                    "redirect": redirect,
                    "plan_type": plan_type,
                    "company_name": company_name,
                    "company_size": company_size,
                    "workspace_name": workspace_name,
                    "mfa_required": False,
                    "remember": remember is not None,
                },
                status_code=400,
            )
            _clear_mfa_signin_challenge_cookie(response)
            return response

        try:
            masked_email = await auth_client.send_login_mfa_email_code(email, password)
            success_message: str | None = (
                f"Verification code sent to {masked_email}"
                if masked_email
                else "Verification code sent to your email."
            )
            response = templates.TemplateResponse(
                request,
                "auth/signin.html",
                {
                    "error": None,
                    "success": success_message,
                    "verified": False,
                    "email": email,
                    "password": password,
                    "redirect": redirect,
                    "plan_type": plan_type,
                    "company_name": company_name,
                    "company_size": company_size,
                    "workspace_name": workspace_name,
                    "mfa_required": True,
                    "remember": remember is not None,
                },
            )
            challenge_token = _create_mfa_signin_challenge(
                email=email,
                password=password,
                redirect=redirect,
                plan_type=plan_type,
                company_name=company_name,
                company_size=company_size,
                workspace_name=workspace_name,
                remember=remember is not None,
            )
            _set_mfa_signin_challenge_cookie(response, challenge_token)
            return response
        except AuthAPIError as e:
            response = templates.TemplateResponse(
                request,
                "auth/signin.html",
                {
                    "error": e.message,
                    "success": None,
                    "verified": False,
                    "email": email,
                    "password": password,
                    "redirect": redirect,
                    "plan_type": plan_type,
                    "company_name": company_name,
                    "company_size": company_size,
                    "workspace_name": workspace_name,
                    "mfa_required": True,
                    "remember": remember is not None,
                },
                status_code=400,
            )
            challenge_token = _create_mfa_signin_challenge(
                email=email,
                password=password,
                redirect=redirect,
                plan_type=plan_type,
                company_name=company_name,
                company_size=company_size,
                workspace_name=workspace_name,
                remember=remember is not None,
            )
            _set_mfa_signin_challenge_cookie(response, challenge_token)
            return response

    # Authenticate via ROPC
    try:
        tokens = await auth_client.login(email, password, otp=otp)
        logger.info("User logged in: email=%s", email)
    except AuthAPIError as e:
        error_message: str | None
        raw_error_message = e.message
        error_code = e.error_code or ""
        if isinstance(raw_error_message, dict):
            error_code = str(raw_error_message.get("error") or error_code)
            error_message = str(
                raw_error_message.get("error_description")
                or raw_error_message.get("detail")
                or raw_error_message.get("message")
                or raw_error_message
            )
        elif isinstance(raw_error_message, str):
            error_message = raw_error_message
        else:
            error_message = str(raw_error_message)
        error_message_lower = f"{error_code} {error_message}".lower()
        mfa_required_error = (
            error_code in {"mfa_required", "totp_required", "invalid_otp"}
            or "mfa_required" in error_message_lower
            or "invalid_otp" in error_message_lower
            or "totp_required" in error_message_lower
            or "mfa" in error_message_lower
            or "otp" in error_message_lower
            or "two-factor" in error_message_lower
        )
        # Provide user-friendly error messages
        if "not verified" in error_message_lower:
            # Redirect to verify page
            return RedirectResponse(
                url=f"/auth/verify?email={email}",
                status_code=303,
            )
        elif mfa_required_error:
            if not otp:
                error_message = None
                success_message = (
                    "Password verified. Enter your authenticator or backup code to continue."
                )
            else:
                error_message = "Invalid verification code."
                success_message = None
        elif error_code == "invalid_grant":
            if otp:
                error_message = "MFA session expired. Enter email and password again."
                success_message = None
                mfa_required_error = False
            else:
                error_message = "Invalid email or password"
                success_message = None
        else:
            success_message = None

        response = templates.TemplateResponse(
            request,
            "auth/signin.html",
            {
                "error": error_message,
                "success": success_message,
                "verified": False,
                "email": email,
                "password": password if mfa_required_error else None,
                "redirect": redirect,
                "plan_type": plan_type,
                "company_name": company_name,
                "company_size": company_size,
                "workspace_name": workspace_name,
                "mfa_required": mfa_required_error,
                "remember": remember is not None,
            },
            status_code=400,
        )
        if mfa_required_error and password:
            challenge_token = _create_mfa_signin_challenge(
                email=email,
                password=password,
                redirect=redirect,
                plan_type=plan_type,
                company_name=company_name,
                company_size=company_size,
                workspace_name=workspace_name,
                remember=remember is not None,
            )
            _set_mfa_signin_challenge_cookie(response, challenge_token)
        else:
            _clear_mfa_signin_challenge_cookie(response)
        return response

    # Get user info
    user_claims = _decode_jwt_payload(tokens.access_token)

    try:
        userinfo = await auth_client.get_userinfo(tokens.access_token)
        user_claims.update(userinfo)
    except AuthAPIError:
        pass  # Continue without userinfo

    user = User.from_jwt_claims(user_claims)

    # Check if user has any tenants, create based on plan type
    result = await db.execute(select(TenantMember).where(TenantMember.user_id == user.id).limit(1))
    membership = result.scalar_one_or_none()

    active_tenant_id = None

    if not membership:
        if not workspace_name:
            # No workspace and no name provided — let the user choose
            # Set auth cookies first so the create-workspace page can authenticate
            response = RedirectResponse(url="/auth/create-workspace", status_code=302)
            cookie_settings = _get_cookie_settings()
            access_max_age = tokens.expires_in
            refresh_max_age = 90 * 24 * 3600 if remember else 30 * 24 * 3600
            response.set_cookie(
                ACCESS_TOKEN_COOKIE, tokens.access_token, max_age=access_max_age, **cookie_settings
            )
            if tokens.refresh_token:
                response.set_cookie(
                    REFRESH_TOKEN_COOKIE,
                    tokens.refresh_token,
                    max_age=refresh_max_age,
                    **cookie_settings,
                )
            user_info = {"id": str(user.id), "email": user.email, "name": user.name}
            response.set_cookie(
                USER_INFO_COOKIE,
                json.dumps(user_info),
                max_age=access_max_age,
                httponly=False,
                secure=cookie_settings.get("secure", True),
                samesite="lax",
                path="/",
            )
            _clear_mfa_signin_challenge_cookie(response)
            return response

        # Workspace name provided (from signup flow) — create immediately
        if plan_type == "enterprise" and company_name:
            tenant_name = workspace_name
            tenant_slug = f"org-{secrets.token_hex(4)}"
            tenant_plan = PlanType.ENTERPRISE
            tenant_settings = {"company_size": company_size}
        else:
            tenant_name = workspace_name
            tenant_slug = f"personal-{str(user.id)[:8]}"
            tenant_plan = PlanType.FREE
            tenant_settings = {}

        tenant = Tenant(
            name=tenant_name,
            slug=tenant_slug,
            plan=tenant_plan,
            settings=tenant_settings,
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        # Create owner membership
        membership = TenantMember(
            organization_id=tenant.id,
            user_id=user.id,
            role=TenantMemberRole.OWNER,
            display_name=user.display_name,
            email=user.email,
        )
        db.add(membership)
        await db.commit()

        active_tenant_id = str(tenant.id)
        logger.info(
            "Created tenant for user %s: slug=%s, plan=%s",
            user.id,
            tenant_slug,
            tenant_plan,
        )
    else:
        active_tenant_id = str(membership.organization_id)

    # Build redirect URL
    redirect_url = redirect or "/dashboard"

    # Create response with cookies
    response = RedirectResponse(url=redirect_url, status_code=302)
    cookie_settings = _get_cookie_settings()

    # Extend cookie lifetime if "remember me" is checked
    access_max_age = tokens.expires_in
    refresh_max_age = 30 * 24 * 3600  # 30 days
    if remember:
        refresh_max_age = 90 * 24 * 3600  # 90 days

    # Set auth cookies
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        tokens.access_token,
        max_age=access_max_age,
        **cookie_settings,
    )

    if tokens.refresh_token:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE,
            tokens.refresh_token,
            max_age=refresh_max_age,
            **cookie_settings,
        )

    # Set active tenant cookie
    response.set_cookie(
        ACTIVE_TENANT_COOKIE,
        active_tenant_id,
        max_age=365 * 24 * 3600,  # 1 year
        **cookie_settings,
    )

    # Set user info cookie (readable by JS)
    user_info = {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
    }
    response.set_cookie(
        USER_INFO_COOKIE,
        json.dumps(user_info),
        max_age=access_max_age,
        httponly=False,  # Allow JS access
        secure=settings.cookie_secure,
        samesite="lax",
    )
    _clear_mfa_signin_challenge_cookie(response)

    return response


@router.get("/create-workspace", response_class=HTMLResponse)
async def create_workspace_form(request: Request):
    """Display workspace creation form for users without a workspace."""
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")
    if not access_token:
        return RedirectResponse(url="/auth/signin", status_code=302)

    return templates.TemplateResponse(
        request,
        "auth/create_workspace.html",
        {"error": None},
    )


@router.post("/create-workspace", response_class=HTMLResponse)
async def create_workspace_submit(
    request: Request,
    workspace_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a workspace for an authenticated user who has none."""
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")
    if not access_token:
        return RedirectResponse(url="/auth/signin", status_code=302)

    user_claims = _decode_jwt_payload(access_token)
    user = User.from_jwt_claims(user_claims)

    # Verify user still has no workspace
    result = await db.execute(select(TenantMember).where(TenantMember.user_id == user.id).limit(1))
    existing = result.scalar_one_or_none()
    if existing:
        return RedirectResponse(url="/dashboard", status_code=302)

    workspace_name = workspace_name.strip()
    if not workspace_name:
        return templates.TemplateResponse(
            request,
            "auth/create_workspace.html",
            {"error": "Workspace name is required"},
            status_code=400,
        )

    tenant = Tenant(
        name=workspace_name,
        slug=f"personal-{str(user.id)[:8]}",
        plan=PlanType.FREE,
        settings={},
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    membership = TenantMember(
        organization_id=tenant.id,
        user_id=user.id,
        role=TenantMemberRole.OWNER,
        display_name=user.display_name,
        email=user.email,
    )
    db.add(membership)
    await db.commit()

    logger.info("Created workspace '%s' for user %s", workspace_name, user.id)

    # Set active tenant cookie and redirect
    cookie_settings = _get_cookie_settings()
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        ACTIVE_TENANT_COOKIE,
        str(tenant.id),
        max_age=365 * 24 * 3600,
        **cookie_settings,
    )
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_form(request: Request):
    """Display forgot password form."""
    return templates.TemplateResponse(
        request,
        "auth/forgot_password.html",
        {"error": None, "success": None},
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Process forgot password form submission."""
    with contextlib.suppress(AuthAPIError):
        await auth_client.forgot_password(email)

    # Always show success message to prevent email enumeration
    return templates.TemplateResponse(
        request,
        "auth/forgot_password.html",
        {
            "error": None,
            "success": "If an account exists with this email, a password reset link has been sent.",
        },
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_form(
    request: Request,
    token: str = Query(""),
):
    """Display reset password form."""
    if not token:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {
                "token": "",
                "error": "Invalid or missing reset token",
                "success": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {
            "token": token,
            "error": None,
            "success": None,
        },
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Process reset password form submission."""
    # Validate passwords match
    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {
                "token": token,
                "error": "Passwords do not match",
                "success": None,
            },
            status_code=400,
        )

    # Reset password via Auth API
    try:
        await auth_client.reset_password(token, password)
    except AuthAPIError as e:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {
                "token": token,
                "error": e.message,
                "success": None,
            },
            status_code=400,
        )

    # Redirect to signin with success message
    return RedirectResponse(
        url="/auth/signin?reset=1",
        status_code=303,
    )


# ===== Account Settings Routes =====


@router.get("/account", response_class=HTMLResponse)
async def account_profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Display account profile page."""
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

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")
    error = request.query_params.get("error")
    success = request.query_params.get("success")

    try:
        profile = await auth_client.get_profile(access_token)
    except AuthAPIError as e:
        profile = None
        error = e.message

    return templates.TemplateResponse(
        request,
        "auth/account_profile.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_tab": "profile",
            "active_section": "account_profile",
            "profile": profile,
            "error": error,
            "success": success,
        },
    )


@router.post("/account", response_class=HTMLResponse)
async def account_profile_update(
    request: Request,
    nickname: str = Form(None),
    given_name: str = Form(None),
    family_name: str = Form(None),
    preferred_username: str = Form(None),
    picture: str = Form(None),
    website: str = Form(None),
    phone_number: str = Form(None),
    zoneinfo: str = Form(None),
    locale: str = Form(None),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Update account profile."""
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

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")

    try:
        await auth_client.update_profile(
            access_token,
            nickname=nickname or None,
            given_name=given_name or None,
            family_name=family_name or None,
            preferred_username=preferred_username or None,
            picture=picture or None,
            website=website or None,
            phone_number=phone_number or None,
            zoneinfo=zoneinfo or None,
            locale=locale or None,
        )
        return RedirectResponse(
            url="/auth/account?success=Profile+updated+successfully", status_code=303
        )
    except AuthAPIError as e:
        # Get profile to redisplay form
        try:
            profile = await auth_client.get_profile(access_token)
        except AuthAPIError:
            profile = None

        return templates.TemplateResponse(
            request,
            "auth/account_profile.html",
            {
                "user": user,
                "tenant": tenant,
                "tenant_member": tenant_member,
                "tenants": tenants,
                "active_tab": "profile",
                "active_section": "account_profile",
                "profile": profile,
                "error": e.message,
                "success": None,
            },
        )


@router.get("/account/security", response_class=HTMLResponse)
async def account_security_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Display account security (MFA) page."""
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

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")
    error = request.query_params.get("error")
    success = request.query_params.get("success")

    try:
        mfa_status = await auth_client.get_mfa_status(access_token)
    except AuthAPIError as e:
        mfa_status = None
        error = e.message

    return templates.TemplateResponse(
        request,
        "auth/account_security.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_tab": "security",
            "active_section": "account_security",
            "mfa_status": mfa_status,
            "totp_setup": None,
            "backup_codes": None,
            "error": error,
            "success": success,
        },
    )


@router.post("/account/security/setup", response_class=HTMLResponse)
async def account_security_setup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Start TOTP setup."""
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

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")

    try:
        totp_setup = await auth_client.setup_totp(access_token)
        mfa_status = await auth_client.get_mfa_status(access_token)
    except AuthAPIError as e:
        return RedirectResponse(
            url=f"/auth/account/security?error={e.message}",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "auth/account_security.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_tab": "security",
            "active_section": "account_security",
            "mfa_status": mfa_status,
            "totp_setup": totp_setup,
            "backup_codes": None,
            "error": None,
            "success": None,
        },
    )


@router.post("/account/security/verify", response_class=HTMLResponse)
async def account_security_verify(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Verify TOTP code and enable MFA."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    user = auth_result.user
    tenant = auth_result.tenant
    tenant_member = auth_result.tenant_member

    # Get user's tenants for switcher
    db_result = await db.execute(
        select(Tenant)
        .join(TenantMember, Tenant.id == TenantMember.organization_id)
        .where(TenantMember.user_id == user.id, Tenant.is_active == True)  # noqa: E712
    )
    tenants = db_result.scalars().all()

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")

    try:
        result = await auth_client.verify_and_enable_totp(access_token, code)
        mfa_status = await auth_client.get_mfa_status(access_token)
    except AuthAPIError as e:
        # Re-setup TOTP on error
        try:
            totp_setup = await auth_client.setup_totp(access_token)
            mfa_status = await auth_client.get_mfa_status(access_token)
        except AuthAPIError:
            totp_setup = None
            mfa_status = None

        return templates.TemplateResponse(
            request,
            "auth/account_security.html",
            {
                "user": user,
                "tenant": tenant,
                "tenant_member": tenant_member,
                "tenants": tenants,
                "active_tab": "security",
                "active_section": "account_security",
                "mfa_status": mfa_status,
                "totp_setup": totp_setup,
                "backup_codes": None,
                "error": e.message,
                "success": None,
            },
        )

    # Show backup codes
    return templates.TemplateResponse(
        request,
        "auth/account_security.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_tab": "security",
            "active_section": "account_security",
            "mfa_status": mfa_status,
            "totp_setup": None,
            "backup_codes": result.backup_codes,
            "error": None,
            "success": None,
        },
    )


@router.post("/account/security/disable", response_class=HTMLResponse)
async def account_security_disable(
    request: Request,
    code: str = Form(...),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Disable MFA."""
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")
    if not access_token:
        return RedirectResponse(url="/auth/login?redirect=/auth/account/security", status_code=302)

    try:
        await auth_client.disable_totp(access_token, code)
        return RedirectResponse(
            url="/auth/account/security?success=Two-factor+authentication+has+been+disabled",
            status_code=303,
        )
    except AuthAPIError as e:
        if e.error_code == "invalid_token" or "expired" in e.message.lower():
            return RedirectResponse(
                url="/auth/login?redirect=/auth/account/security", status_code=302
            )
        return RedirectResponse(
            url=f"/auth/account/security?error={e.message}",
            status_code=303,
        )


@router.post("/account/security/regenerate-codes", response_class=HTMLResponse)
async def account_security_regenerate_codes(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Regenerate backup codes."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    user = auth_result.user
    tenant = auth_result.tenant
    tenant_member = auth_result.tenant_member

    # Get user's tenants for switcher
    db_result = await db.execute(
        select(Tenant)
        .join(TenantMember, Tenant.id == TenantMember.organization_id)
        .where(TenantMember.user_id == user.id, Tenant.is_active == True)  # noqa: E712
    )
    tenants = db_result.scalars().all()

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")

    try:
        backup_codes = await auth_client.regenerate_backup_codes(access_token, code)
        mfa_status = await auth_client.get_mfa_status(access_token)
    except AuthAPIError as e:
        return RedirectResponse(
            url=f"/auth/account/security?error={e.message}",
            status_code=303,
        )

    return templates.TemplateResponse(
        request,
        "auth/account_security.html",
        {
            "user": user,
            "tenant": tenant,
            "tenant_member": tenant_member,
            "tenants": tenants,
            "active_tab": "security",
            "active_section": "account_security",
            "mfa_status": mfa_status,
            "totp_setup": None,
            "backup_codes": backup_codes,
            "error": None,
            "success": "Backup codes have been regenerated",
        },
    )


@router.get("/account/password")
async def account_password_page():
    """Redirect to security page (password is now part of security)."""
    return RedirectResponse(url="/auth/account/security", status_code=302)


@router.post("/account/password")
async def account_password_change(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    auth_result: WebAuthContext | RedirectResponse = Depends(get_web_auth_context),
    auth_client: AuthAPIClient = Depends(get_auth_api_client),
):
    """Change password (redirects back to security page)."""
    if isinstance(auth_result, RedirectResponse):
        return auth_result

    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE, "")

    # Validate passwords match
    if new_password != confirm_password:
        return RedirectResponse(
            url="/auth/account/security?error=Passwords+do+not+match",
            status_code=303,
        )

    try:
        await auth_client.change_password(access_token, current_password, new_password)
        return RedirectResponse(
            url="/auth/account/security?success=Password+changed+successfully",
            status_code=303,
        )
    except AuthAPIError as e:
        return RedirectResponse(
            url=f"/auth/account/security?error={e.message}",
            status_code=303,
        )
