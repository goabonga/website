# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 login/logout routes for the web UI."""

import secrets
from typing import Annotated
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apt_server.config import settings
from apt_server.database import get_db
from apt_server.logging import get_logger
from apt_server.services.session import (
    create_session_cookie,
    create_state_cookie,
    generate_pkce,
    read_state_cookie,
)

logger = get_logger(__name__)

router = APIRouter(tags=["auth"], include_in_schema=False)


def _issuer() -> str:
    return settings.oauth2_issuer.rstrip("/")


def _callback_url(request: Request) -> str:
    """Build the OAuth2 callback URL, forcing https behind a reverse proxy."""
    url = request.url_for("callback")
    if url.scheme == "http" and request.headers.get("x-forwarded-proto") == "https":
        url = url.replace(scheme="https")
    return str(url)


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect the user to the auth service's OAuth2 authorize endpoint."""
    if not settings.oauth2_issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OAuth2 not configured"
        )

    state = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce()
    callback_url = _callback_url(request)

    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oauth2_swagger_client_id or settings.oauth2_client_id,
            "redirect_uri": callback_url,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    response = RedirectResponse(url=f"{_issuer()}/oauth2/authorize?{params}")
    response.set_cookie(
        key="oauth_state",
        value=create_state_cookie(state, verifier),
        max_age=600,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str,
    state: str,
) -> RedirectResponse:
    """Handle the OAuth2 callback: exchange code for token, set session cookie."""
    state_cookie = request.cookies.get("oauth_state")
    if not state_cookie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing state cookie")

    saved = read_state_cookie(state_cookie)
    if saved is None or saved[0] != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid state")

    _, verifier = saved
    callback_url = _callback_url(request)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_issuer()}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_url,
                "client_id": settings.oauth2_swagger_client_id or settings.oauth2_client_id,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"token exchange failed: {resp.text}",
        )

    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="no access_token in response"
        )

    # Resolve user profile from userinfo endpoint
    display_name = ""
    user_name = ""
    avatar_url = ""
    userinfo: dict = {}

    try:
        async with httpx.AsyncClient(timeout=5.0) as userinfo_client:
            ui_resp = await userinfo_client.get(
                f"{_issuer()}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if ui_resp.status_code == 200:
                userinfo = ui_resp.json()
    except Exception as exc:
        logger.warning("userinfo request failed: %s", exc)

    if userinfo:
        display_name = userinfo.get("email") or userinfo.get("preferred_username") or ""
        user_name = (
            userinfo.get("nickname")
            or userinfo.get("name")
            or userinfo.get("preferred_username")
            or ""
        )
        picture = userinfo.get("picture") or ""
        if picture:
            avatar_url = picture if picture.startswith("http") else f"{_issuer()}{picture}"

    # Fallback: use issuer with Gravatar-style identicon
    if not avatar_url and display_name and "@" in display_name:
        import hashlib as _hashlib

        email_hash = _hashlib.md5(display_name.strip().lower().encode()).hexdigest()
        avatar_url = f"https://www.gravatar.com/avatar/{email_hash}?s=80&d=identicon"

    logger.info(
        "session user: name=%s email=%s avatar=%s", user_name, display_name, bool(avatar_url)
    )

    # Resolve sub from the access token and upsert user cache
    try:
        token_claims = jwt.decode(access_token, options={"verify_signature": False})
        user_sub = token_claims.get("sub", "")
        if user_sub and display_name:
            from apt_server.services import user_cache

            await user_cache.upsert(
                db, sub=user_sub, email=display_name, name=user_name, avatar_url=avatar_url
            )
    except Exception as exc:
        logger.warning("failed to cache user profile: %s", exc)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_cookie(
            access_token,
            display_name=display_name,
            name=user_name,
            avatar_url=avatar_url,
        ),
        max_age=settings.session_max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Clear the session cookie and redirect to the landing page."""
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
