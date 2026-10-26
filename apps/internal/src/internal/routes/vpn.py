# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""VPN admin routes for HTML pages.

Scopes required:
- vpn:admin - View and manage VPN sessions
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from internal import TEMPLATES_DIR
from internal.auth.dependencies import require_scope_or_redirect
from internal.auth.models import User
from internal.config import settings
from internal.logging import get_logger
from internal.services.vpn_portal_client import vpn_portal_client

router = APIRouter(prefix="/vpn", tags=["vpn"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

require_vpn_admin = require_scope_or_redirect("vpn:admin")


@router.get("/sessions", response_class=HTMLResponse)
async def vpn_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    auth_result: User | RedirectResponse = Depends(require_vpn_admin),
):
    """List all VPN sessions with pagination."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result
    per_page = 20

    logger.info(
        "VPN sessions accessed | user_id=%s client_id=%s page=%d",
        user.id,
        settings.oauth2_client_id,
        page,
    )

    # Fetch sessions from VPN Portal API
    sessions_response = await vpn_portal_client.get_sessions(
        page=page,
        per_page=per_page,
    )

    sessions = []
    total = 0
    error = None

    if sessions_response:
        sessions = sessions_response.sessions
        total = sessions_response.total
    else:
        error = "Failed to fetch VPN sessions. The VPN Portal service may be unavailable."

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return templates.TemplateResponse(
        request=request,
        name="admin/vpn/sessions.html",
        context={
            "request": request,
            "active_section": "vpn",
            "user": user,
            "sessions": sessions,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "now": datetime.now(UTC),
            "success": request.query_params.get("success"),
            "error": error or request.query_params.get("error"),
        },
    )


@router.post("/sessions/{serial_number}/revoke")
async def revoke_vpn_session(
    request: Request,
    serial_number: str,
    auth_result: User | RedirectResponse = Depends(require_vpn_admin),
):
    """Revoke a VPN session by certificate serial number."""
    if not isinstance(auth_result, User):
        return auth_result

    user = auth_result

    success = await vpn_portal_client.revoke_session(serial_number)

    if success:
        logger.info(
            "VPN session revoked | user_id=%s client_id=%s serial_number=%s",
            user.id,
            settings.oauth2_client_id,
            serial_number,
        )
        return RedirectResponse(
            url="/vpn/sessions?success=Session+revoked+successfully",
            status_code=303,
        )
    else:
        logger.warning(
            "Failed to revoke VPN session | user_id=%s serial_number=%s",
            user.id,
            serial_number,
        )
        return RedirectResponse(
            url="/vpn/sessions?error=Failed+to+revoke+session",
            status_code=303,
        )
