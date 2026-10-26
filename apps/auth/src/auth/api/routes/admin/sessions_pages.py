# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin sessions management HTML pages."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_templates, get_user_admin_permissions, require_scope
from auth.db.models.rbac import Role
from auth.db.models.user import Session, User
from auth.db.repositories.session import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions")

_session_repo = SessionRepository()

# Scope dependencies
require_sessions_read = require_scope("sessions:read", redirect_to_login=True)
require_sessions_revoke = require_scope("sessions:revoke", redirect_to_login=True)


def _primary_email_from_user(user: User | None) -> str | None:
    """Return the primary email of ``user`` (or the first email if none flagged)."""
    if user is None or not user.emails:
        return None
    for email in user.emails:
        if email.is_primary:
            return email.email
    return user.emails[0].email


def session_to_dict(session: Session, user_email: str | None = None) -> dict:
    """Convert Session model to dictionary format.

    Args:
        session: Session database model.
        user_email: Optional user email.

    Returns:
        Dictionary with session information.
    """
    now = datetime.now(UTC)
    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "user_email": user_email,
        "ip_address": session.ip_address,
        "user_agent": session.user_agent,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
        "is_active": session.revoked_at is None and session.expires_at > now,
    }


def parse_user_agent(user_agent: str | None) -> dict:
    """Parse user agent string into browser and OS info.

    Args:
        user_agent: User agent string.

    Returns:
        Dictionary with browser and os info.
    """
    if not user_agent:
        return {"browser": "Unknown", "os": "Unknown"}

    browser = "Unknown"
    os = "Unknown"

    # Detect browser
    if "Firefox" in user_agent:
        browser = "Firefox"
    elif "Chrome" in user_agent and "Edg" not in user_agent:
        browser = "Chrome"
    elif "Safari" in user_agent and "Chrome" not in user_agent:
        browser = "Safari"
    elif "Edg" in user_agent:
        browser = "Edge"
    elif "Opera" in user_agent or "OPR" in user_agent:
        browser = "Opera"

    # Detect OS
    if "Windows" in user_agent:
        os = "Windows"
    elif "Mac OS" in user_agent or "Macintosh" in user_agent:
        os = "macOS"
    elif "Linux" in user_agent:
        os = "Linux"
    elif "Android" in user_agent:
        os = "Android"
    elif "iOS" in user_agent or "iPhone" in user_agent or "iPad" in user_agent:
        os = "iOS"

    return {"browser": browser, "os": os}


@router.get("", response_class=HTMLResponse)
async def sessions_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_sessions_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    active_only: Annotated[bool, Query()] = True,
) -> HTMLResponse:
    """Sessions list page."""
    logger.debug("Admin page: listing sessions")
    templates = get_templates()

    limit = 20

    sessions, total = await _session_repo.list(
        db,
        page=page,
        page_size=limit,
        active_only=active_only,
        with_user=True,
    )

    sessions_list = []
    for session in sessions:
        user_email = _primary_email_from_user(session.user)
        session_dict = session_to_dict(session, user_email)
        session_dict["parsed_ua"] = parse_user_agent(session.user_agent)
        sessions_list.append(session_dict)

    # Calculate pagination
    total_pages = (total + limit - 1) // limit

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/sessions/list.html",
        context={
            "active_section": "sessions",
            "sessions": sessions_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "active_only": active_only,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/{session_id}", response_class=HTMLResponse)
async def session_detail_page(
    request: Request,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_sessions_read)],
) -> HTMLResponse:
    """Session detail page."""
    logger.debug("Admin page: viewing session id=%s", session_id)
    templates = get_templates()

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await _session_repo.find_by_id_with_user(db, session_uuid)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    user_email = _primary_email_from_user(session.user)

    session_dict = session_to_dict(session, user_email)
    session_dict["parsed_ua"] = parse_user_agent(session.user_agent)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/sessions/detail.html",
        context={
            "active_section": "sessions",
            "session": session_dict,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{session_id}/revoke", response_class=RedirectResponse)
async def session_revoke_submit(
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_sessions_revoke)],
) -> RedirectResponse:
    """Handle session revocation."""
    logger.debug("Admin page: revoking session id=%s", session_id)

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/sessions?error=Invalid+session+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    session = await _session_repo.find_by_id(db, session_uuid)

    if not session:
        return RedirectResponse(
            url="/admin/sessions?error=Session+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if session.revoked_at:
        return RedirectResponse(
            url=f"/admin/sessions/{session_id}?error=Session+already+revoked",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _session_repo.revoke(db, session)
    await db.commit()

    logger.info("Admin page: revoked session id=%s", session_id)
    return RedirectResponse(
        url="/admin/sessions?success=Session+revoked+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/revoke-all", response_class=RedirectResponse)
async def sessions_revoke_all_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_sessions_revoke)],
    user_id: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle bulk session revocation."""
    logger.debug("Admin page: revoking all sessions (user_id=%s)", user_id)

    user_uuid: uuid.UUID | None = None
    if user_id:
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return RedirectResponse(
                url="/admin/sessions?error=Invalid+user+ID",
                status_code=status.HTTP_303_SEE_OTHER,
            )

    sessions = await _session_repo.list_active(db, user_id=user_uuid)

    await _session_repo.revoke_many(db, sessions)
    await db.commit()

    logger.info("Admin page: revoked %d sessions", len(sessions))
    return RedirectResponse(
        url=f"/admin/sessions?success=Revoked+{len(sessions)}+session(s)",
        status_code=status.HTTP_303_SEE_OTHER,
    )
