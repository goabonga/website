# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Federation callback endpoint for handling IdP responses."""

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.config import settings
from auth.services.federation import federation_service
from auth.services.session import SessionService, hash_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _login_error_url(message: str) -> str:
    """The login page URL announcing a failed federation, with the reason url-encoded."""
    return "/auth/login?" + urlencode(
        {"error": "federation_failed", "message": message}, quote_via=quote
    )


@router.get("/callback")
async def federation_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = Query(None, description="Authorization code from IdP"),
    state: str | None = Query(None, description="State parameter"),
    error: str | None = Query(None, description="Error code from IdP"),
    error_description: str | None = Query(None, description="Error description from IdP"),
) -> RedirectResponse:
    """Handle callback from external identity provider.

    This endpoint receives the authorization code from the IdP,
    exchanges it for tokens, extracts user info, and performs
    JIT provisioning or account linking.
    """
    # Handle error responses from IdP
    if error:
        logger.warning(
            "Federation error from IdP: error=%s, description=%s", error, error_description
        )
        # Redirect to login page with error
        error_msg = error_description or error
        return RedirectResponse(
            url=_login_error_url(error_msg),
            status_code=status.HTTP_302_FOUND,
        )

    # Validate required parameters
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameters: code and state",
        )

    # Decode state
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state).decode())
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Failed to decode federation state: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    tenant_slug = state_data.get("tenant_slug")
    idp_id = state_data.get("idp_id")
    code_verifier = state_data.get("code_verifier")
    original_state = state_data.get("original_state")
    redirect_uri = state_data.get("redirect_uri")

    if not tenant_slug or not idp_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state: missing tenant or IdP information",
        )

    # Get IdP configuration
    idp = await federation_service.get_identity_provider(db, idp_id)
    if not idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    # Build callback URL (must match the one used in authorization request)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    callback_url = f"{scheme}://{host}/federation/callback"

    try:
        # Exchange code for tokens
        logger.info("Exchanging authorization code for tokens: idp=%s", idp.name)
        token_response = await federation_service.exchange_code_for_tokens(
            idp=idp,
            code=code,
            callback_url=callback_url,
            code_verifier=code_verifier,
        )

        access_token = token_response.get("access_token")
        id_token = token_response.get("id_token")

        if not access_token:
            raise ValueError("No access token in response")

        # Get user info from IdP
        logger.info("Fetching user info from IdP: idp=%s", idp.name)
        user_info = await federation_service.get_user_info(
            idp=idp,
            access_token=access_token,
            id_token=id_token,
        )

        logger.info(
            "User info received: subject=%s, email=%s",
            user_info.subject,
            user_info.email,
        )

        # Find or create user (JIT provisioning)
        user, federated_identity, is_new_user = await federation_service.find_or_create_user(
            db=db,
            idp=idp,
            user_info=user_info,
            tenant_slug=tenant_slug,
        )

        logger.info(
            "User authenticated via federation: user_id=%s, is_new=%s, idp=%s",
            user.id,
            is_new_user,
            idp.name,
        )

        # Create local session for the user
        session_service = SessionService()
        session_token = session_service.generate_session_token()
        csrf_token = session_service.generate_csrf_token()

        from auth.db.models.user import Session

        session = Session(
            user_id=user.id,
            session_token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_expiry_days),
        )
        await session_service.add(db, session)
        await db.commit()

        # Determine redirect URL
        if redirect_uri:
            final_redirect = redirect_uri
            # Add state if provided
            if original_state:
                separator = "&" if "?" in final_redirect else "?"
                final_redirect = f"{final_redirect}{separator}state={original_state}"
        else:
            # Default to user settings page
            final_redirect = "/auth/settings"

        # Create response with session cookie
        response = RedirectResponse(url=final_redirect, status_code=status.HTTP_302_FOUND)

        # Set session cookie
        from auth.middlewares.tenant import (
            get_csrf_cookie_name,
            get_session_cookie_domain,
            get_session_cookie_name,
        )

        cookie_domain = get_session_cookie_domain()
        response.set_cookie(
            key=get_session_cookie_name(),
            value=session_token,
            max_age=settings.session_expiry_days * 24 * 60 * 60,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            domain=cookie_domain,
        )

        # Set CSRF cookie (readable by JS for forms)
        response.set_cookie(
            key=get_csrf_cookie_name(),
            value=csrf_token,
            max_age=settings.session_expiry_days * 24 * 60 * 60,
            httponly=False,  # JS needs to read this
            secure=settings.session_cookie_secure,
            samesite="strict",
            domain=cookie_domain,
        )

        return response

    except ValueError as e:
        logger.error("Federation failed: %s", e)
        return RedirectResponse(
            url=_login_error_url(str(e)),
            status_code=status.HTTP_302_FOUND,
        )
    except Exception as e:
        logger.exception("Unexpected error during federation: %s", e)
        return RedirectResponse(
            url=_login_error_url("An unexpected error occurred"),
            status_code=status.HTTP_302_FOUND,
        )
