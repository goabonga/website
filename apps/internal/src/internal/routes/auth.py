# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 authentication routes for HTML pages."""

import json
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE
from internal.config import settings
from internal.logging import get_logger

# Cookie name for user info
USER_INFO_COOKIE = "user_info"

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _generate_pkce_verifier() -> str:
    """Generate a PKCE code verifier (RFC 7636)."""
    import secrets

    return secrets.token_urlsafe(64)[:128]


def _generate_pkce_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from verifier (S256 method)."""
    import base64
    import hashlib

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@router.get("/login")
async def login(request: Request, redirect: str = Query(default="/")):
    """Redirect to OAuth2 authorization endpoint."""
    import secrets
    from urllib.parse import urlencode

    state = secrets.token_urlsafe(32)
    code_verifier = _generate_pkce_verifier()
    code_challenge = _generate_pkce_challenge(code_verifier)

    # Use the public frontend client with PKCE
    # Only request basic OIDC scopes - elevated scopes are obtained via token exchange
    issuer = settings.oauth2_issuer.rstrip("/")
    params = {
        "client_id": settings.oauth2_frontend_client_id,
        "response_type": "code",
        "redirect_uri": f"{settings.app_base_url}/auth/callback",
        "scope": "openid profile email offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{issuer}/oauth2/authorize?{urlencode(params)}"

    logger.info(
        "Login initiated | client_id=%s redirect=%s",
        settings.oauth2_frontend_client_id,
        redirect,
    )

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        "oauth_redirect",
        redirect,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        "oauth_code_verifier",
        code_verifier,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


# PKCE-related errors that should redirect to login instead of showing error page
PKCE_ERROR_KEYWORDS = [
    "pkce",
    "code_challenge",
    "code_verifier",
]


def _is_pkce_related_error(error: str | None, error_description: str | None) -> bool:
    """Check if the error is PKCE-related and should trigger a new login flow."""
    if not error and not error_description:
        return False

    combined = f"{error or ''} {error_description or ''}".lower()
    return any(keyword in combined for keyword in PKCE_ERROR_KEYWORDS)


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
):
    """OAuth2 callback - exchange authorization code for tokens."""
    # Handle OAuth2 error response
    if error:
        logger.warning("OAuth2 error: %s - %s", error, error_description)

        # For PKCE-related errors, redirect to login to start fresh flow
        if _is_pkce_related_error(error, error_description):
            logger.info("PKCE error detected, redirecting to login")
            redirect_url = oauth_redirect or "/"
            # Clear stale OAuth cookies
            response = RedirectResponse(
                url=f"/auth/login?redirect={quote(redirect_url, safe='/')}",
                status_code=status.HTTP_302_FOUND,
            )
            response.delete_cookie("oauth_state")
            response.delete_cookie("oauth_redirect")
            response.delete_cookie("oauth_code_verifier")
            return response

        return templates.TemplateResponse(
            request=request,
            name="auth/error.html",
            context={
                "request": request,
                "error": error,
                "error_description": error_description or "An authentication error occurred.",
            },
        )

    # Check for required parameters
    if not code or not state:
        logger.warning("Missing code or state in callback")
        return templates.TemplateResponse(
            request=request,
            name="auth/error.html",
            context={
                "request": request,
                "error": "invalid_request",
                "error_description": "Missing authorization code or state parameter.",
            },
        )

    # Verify state to prevent CSRF
    # If state cookie is missing (expired), redirect to login to start fresh
    if oauth_state is None:
        logger.warning("OAuth state cookie missing (likely expired), redirecting to login")
        redirect_url = oauth_redirect or "/"
        response = RedirectResponse(
            url=f"/auth/login?redirect={quote(redirect_url, safe='/')}",
            status_code=status.HTTP_302_FOUND,
        )
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_redirect")
        response.delete_cookie("oauth_code_verifier")
        return response

    if state != oauth_state:
        logger.warning("OAuth state mismatch: expected %s, got %s", oauth_state, state)
        return templates.TemplateResponse(
            request=request,
            name="auth/error.html",
            context={
                "request": request,
                "error": "invalid_state",
                "error_description": "Invalid OAuth state. Please try logging in again.",
            },
        )

    # Verify PKCE code verifier is present
    # If missing (cookie expired), redirect to login to start fresh flow
    if not oauth_code_verifier:
        logger.warning("Missing PKCE code verifier (cookie expired), redirecting to login")
        redirect_url = oauth_redirect or "/"
        response = RedirectResponse(
            url=f"/auth/login?redirect={quote(redirect_url, safe='/')}",
            status_code=status.HTTP_302_FOUND,
        )
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_redirect")
        response.delete_cookie("oauth_code_verifier")
        return response

    # Exchange code for tokens
    issuer = settings.oauth2_issuer.rstrip("/")
    token_url = f"{issuer}/oauth2/token"

    try:
        async with httpx.AsyncClient() as client:
            # Use the public frontend client with PKCE (no client_secret)
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{settings.app_base_url}/auth/callback",
                    "client_id": settings.oauth2_frontend_client_id,
                    "code_verifier": oauth_code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )

            if token_response.status_code != 200:
                logger.error(
                    "Token exchange failed: %s %s",
                    token_response.status_code,
                    token_response.text,
                )
                return templates.TemplateResponse(
                    request=request,
                    name="auth/error.html",
                    context={
                        "request": request,
                        "error": "token_exchange_failed",
                        "error_description": "Failed to exchange authorization code. Please try again.",
                    },
                )

            tokens = token_response.json()

    except httpx.RequestError as e:
        logger.error("Token exchange request failed: %s", e)
        return templates.TemplateResponse(
            request=request,
            name="auth/error.html",
            context={
                "request": request,
                "error": "server_error",
                "error_description": "Failed to connect to authentication server. Please try again later.",
            },
        )

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    if not access_token:
        return templates.TemplateResponse(
            request=request,
            name="auth/error.html",
            context={
                "request": request,
                "error": "no_token",
                "error_description": "No access token received from authentication server.",
            },
        )

    # Fetch user info from userinfo endpoint
    user_info = None
    userinfo_url = f"{issuer}/userinfo"
    try:
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            if userinfo_response.status_code == 200:
                userinfo_data = userinfo_response.json()
                user_info = {
                    "name": userinfo_data.get("name"),
                    "email": userinfo_data.get("email"),
                    "picture": userinfo_data.get("picture"),
                }
                logger.debug("Fetched user info: %s", user_info)
    except Exception as e:
        logger.warning("Failed to fetch user info: %s", e)

    # Redirect to original URL or default
    redirect_url = oauth_redirect or "/"

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    # Set access token cookie
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=expires_in,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )

    # Set refresh token cookie if provided
    if refresh_token:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE,
            refresh_token,
            max_age=30 * 24 * 3600,  # 30 days
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )

    # Set user info cookie (not httponly so it can be read by JS if needed)
    if user_info:
        response.set_cookie(
            USER_INFO_COOKIE,
            json.dumps(user_info),
            max_age=expires_in,
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
        )

    # Clear OAuth state cookies
    response.delete_cookie("oauth_state")
    response.delete_cookie("oauth_redirect")
    response.delete_cookie("oauth_code_verifier")

    # Extract user_id from user_info if available
    user_id = None
    if user_info and user_info.get("email"):
        user_id = user_info.get("email")

    logger.info(
        "User authenticated successfully | client_id=%s user=%s redirect=%s",
        settings.oauth2_frontend_client_id,
        user_id,
        redirect_url,
    )
    return response


@router.get("/logout")
async def logout(redirect: str = Query(default="/auth/login")):
    """Logout - clear authentication cookies."""
    response = RedirectResponse(url=redirect, status_code=status.HTTP_302_FOUND)

    # Clear all auth cookies
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    response.delete_cookie(REFRESH_TOKEN_COOKIE)
    response.delete_cookie(USER_INFO_COOKIE)
    response.delete_cookie("oauth_state")
    response.delete_cookie("oauth_redirect")
    response.delete_cookie("oauth_code_verifier")

    logger.info(
        "User logged out | client_id=%s redirect=%s",
        settings.oauth2_frontend_client_id,
        redirect,
    )
    return response


@router.get("/refresh")
async def refresh_token(
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_TOKEN_COOKIE),
):
    """Refresh access token using refresh token."""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    issuer = settings.oauth2_issuer.rstrip("/")
    token_url = f"{issuer}/oauth2/token"

    try:
        async with httpx.AsyncClient() as client:
            # Use the public frontend client (no client_secret for public clients)
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.oauth2_frontend_client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )

            if token_response.status_code != 200:
                logger.warning("Token refresh failed: %s", token_response.status_code)
                # Clear cookies and redirect to login
                resp = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
                resp.delete_cookie(ACCESS_TOKEN_COOKIE)
                resp.delete_cookie(REFRESH_TOKEN_COOKIE)
                return resp

            tokens = token_response.json()

    except httpx.RequestError as e:
        logger.error("Token refresh request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to auth server",
        )

    access_token = tokens.get("access_token")
    new_refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    # Redirect back to referer or admin
    referer = request.headers.get("referer", "/")

    response = RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)

    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=expires_in,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )

    if new_refresh_token:
        response.set_cookie(
            REFRESH_TOKEN_COOKIE,
            new_refresh_token,
            max_age=30 * 24 * 3600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
        )

    logger.info(
        "Token refreshed | client_id=%s",
        settings.oauth2_frontend_client_id,
    )

    return response
