# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Logout endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_session_service
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import get_session_cookie_name, get_tenant_context
from auth.services.session import SessionService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event


def _get_current_tenant_id() -> str | None:
    ctx = get_tenant_context()
    return ctx.tenant_id if ctx else None


logger = logging.getLogger(__name__)

router = APIRouter()


def _clear_session_cookies(response: Response) -> None:
    """Clear session cookies from response."""
    from auth.middlewares.tenant import (
        get_csrf_cookie_name,
        get_session_cookie_domain,
        get_session_cookie_name,
    )

    cookie_domain = get_session_cookie_domain()
    response.delete_cookie(
        key=get_session_cookie_name(),
        path="/",
        domain=cookie_domain,
    )
    response.delete_cookie(
        key=get_csrf_cookie_name(),
        path="/",
        domain=cookie_domain,
    )


@router.post("/logout")
async def logout_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
) -> RedirectResponse:
    """Terminate the current session and redirect to the login page.

    Reads the session cookie, revokes the corresponding session row in the
    database, and deletes both the session and CSRF cookies from the browser.
    Dispatches ``LOGOUT`` and ``SESSION_REVOKED`` webhook events before
    redirecting. If no session cookie is present the cookies are still cleared
    and the redirect is issued without error.

    **Specification:** RFC 6265 §4.1 (Set-Cookie deletion via ``Max-Age=0``)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt -c cookies.txt -X POST \\
      https://auth.example.com/auth/logout -L
    ```
    """
    logger.debug("Logout form submitted")
    # Get session token from cookie
    session_token = request.cookies.get(get_session_cookie_name())

    if session_token:
        # Get user info before revoking for logging
        user = await session_service.get_user_by_session_token(db, session_token)
        user_id = str(user.id) if user else "unknown"
        logger.info("ACTION: user_logout, user_id=%s", user_id)
        # Revoke the session
        await session_service.revoke_session(db, session_token)

        tenant_id = _get_current_tenant_id()
        logout_data = {
            "user_id": user_id,
            "tenant_id": tenant_id,
        }
        await dispatch_webhook_event(
            db, tenant_id=tenant_id, event=WebhookEvent.LOGOUT, data=logout_data
        )
        await dispatch_webhook_event(
            db, tenant_id=tenant_id, event=WebhookEvent.SESSION_REVOKED, data=logout_data
        )
        await db.commit()
        logger.debug("Logout: session revoked successfully for user_id=%s", user_id)
    else:
        logger.debug("Logout: no session token found")

    # Redirect to login page
    response = RedirectResponse(
        url="/auth/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_session_cookies(response)

    return response


@router.post("/logout/api")
async def logout_api(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
) -> Response:
    """Terminate the current session and return a JSON confirmation.

    Requires a valid session cookie; returns ``401`` if no cookie is present or
    if the session token cannot be revoked. On success the session row is
    deleted from the database, both the session and CSRF cookies are cleared in
    the response, and ``LOGOUT`` / ``SESSION_REVOKED`` webhook events are
    dispatched. Designed for SPA and native clients that prefer a JSON response
    over a browser redirect.

    **Specification:** RFC 6265 §4.1 (Set-Cookie deletion via ``Max-Age=0``)

    **Authentication:** session cookie (RFC 6265)

    **Responses:**
    - ``200`` — logged out successfully, cookies cleared
    - ``401`` — missing or invalid session cookie

    **Example:**
    ```
    curl -b cookies.txt -c cookies.txt -X POST \\
      https://auth.example.com/auth/logout/api
    ```
    """
    logger.debug("API logout request received")
    # Get session token from cookie
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        logger.warning("API logout failed: not authenticated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Get user info before revoking for logging
    user = await session_service.get_user_by_session_token(db, session_token)

    # Revoke the session
    revoked = await session_service.revoke_session(db, session_token)

    if not revoked:
        await db.commit()
        logger.warning("API logout failed: invalid session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    user_id = str(user.id) if user else "unknown"
    tenant_id = _get_current_tenant_id()
    logout_data = {"user_id": user_id, "tenant_id": tenant_id}
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.LOGOUT, data=logout_data
    )
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.SESSION_REVOKED, data=logout_data
    )
    await db.commit()

    logger.info("ACTION: user_logout_api, user_id=%s", user_id)

    # Return response with cleared cookies
    response = Response(
        content='{"message": "Logged out successfully"}',
        media_type="application/json",
    )
    _clear_session_cookies(response)

    return response


@router.post("/logout/all")
async def logout_all_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
) -> RedirectResponse:
    """Revoke every active session for the user and redirect to the login page.

    Resolves the authenticated user from the session cookie, then calls
    ``revoke_all_user_sessions`` to invalidate all their sessions across every
    device and browser. Both the session and CSRF cookies are deleted from the
    current browser. ``LOGOUT`` and ``SESSION_REVOKED`` webhook events are
    dispatched with the count of revoked sessions before the ``303`` redirect.
    If no session cookie is present the cookies are still cleared and the
    redirect is issued without error.

    **Specification:** RFC 6265 §4.1 (Set-Cookie deletion via ``Max-Age=0``)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt -c cookies.txt -X POST \\
      https://auth.example.com/auth/logout/all -L
    ```
    """
    logger.debug("Logout all sessions form submitted")
    # Get session token from cookie
    session_token = request.cookies.get(get_session_cookie_name())

    if session_token:
        # Get user from session
        user = await session_service.get_user_by_session_token(db, session_token)

        if user:
            logger.info("ACTION: user_logout_all, user_id=%s", user.id)
            # Revoke all user sessions
            count = await session_service.revoke_all_user_sessions(db, str(user.id))

            tenant_id = _get_current_tenant_id()
            event_data = {
                "user_id": str(user.id),
                "tenant_id": tenant_id,
                "sessions_revoked": count,
            }
            await dispatch_webhook_event(
                db, tenant_id=tenant_id, event=WebhookEvent.LOGOUT, data=event_data
            )
            await dispatch_webhook_event(
                db,
                tenant_id=tenant_id,
                event=WebhookEvent.SESSION_REVOKED,
                data=event_data,
            )
            await db.commit()
            logger.debug("All %d sessions revoked for user_id=%s", count, user.id)
    else:
        logger.debug("Logout all: no session token found")

    # Redirect to login page
    response = RedirectResponse(
        url="/auth/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_session_cookies(response)

    return response


@router.post("/logout/all/api")
async def logout_all_api(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_service: SessionService = Depends(get_session_service),
) -> Response:
    """Revoke every active session for the user and return a JSON confirmation.

    Requires a valid session cookie; returns ``401`` if no cookie is present or
    the session cannot be resolved to a user. Calls
    ``revoke_all_user_sessions`` to invalidate all sessions across every device,
    clears the session and CSRF cookies on the current response, and dispatches
    ``LOGOUT`` / ``SESSION_REVOKED`` webhook events. The response body includes
    the count of revoked sessions. Designed for SPA and native clients that
    prefer a JSON response over a browser redirect.

    **Specification:** RFC 6265 §4.1 (Set-Cookie deletion via ``Max-Age=0``)

    **Authentication:** session cookie (RFC 6265)

    **Responses:**
    - ``200`` — all sessions revoked, cookies cleared; body contains session count
    - ``401`` — missing or invalid session cookie

    **Example:**
    ```
    curl -b cookies.txt -c cookies.txt -X POST \\
      https://auth.example.com/auth/logout/all/api
    ```
    """
    logger.debug("API logout all sessions request received")
    # Get session token from cookie
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        logger.warning("API logout all failed: not authenticated")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Get user from session
    user = await session_service.get_user_by_session_token(db, session_token)

    if not user:
        logger.warning("API logout all failed: invalid session")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    logger.info("ACTION: user_logout_all_api, user_id=%s", user.id)

    # Revoke all user sessions
    count = await session_service.revoke_all_user_sessions(db, str(user.id))

    tenant_id = _get_current_tenant_id()
    event_data = {
        "user_id": str(user.id),
        "tenant_id": tenant_id,
        "sessions_revoked": count,
    }
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.LOGOUT, data=event_data
    )
    await dispatch_webhook_event(
        db, tenant_id=tenant_id, event=WebhookEvent.SESSION_REVOKED, data=event_data
    )
    await db.commit()

    logger.info(
        "ACTION: user_logout_all_api_complete, user_id=%s, sessions_revoked=%d", user.id, count
    )

    # Return response with cleared cookies
    response = Response(
        content=f'{{"message": "Logged out from {count} session(s)"}}',
        media_type="application/json",
    )
    _clear_session_cookies(response)

    return response
