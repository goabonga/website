# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin dashboard page."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_oauth2_client_service,
    get_session_service,
    get_templates,
    get_user_admin_permissions,
    get_user_service,
    require_scope,
)
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.role import role_service
from auth.services.session import SessionService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter()

# Require any admin scope to view dashboard
require_admin_read = require_scope("users:read", redirect_to_login=True)


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_admin_read)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    oauth2_client_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
) -> HTMLResponse:
    """Admin dashboard with system statistics.

    Renders the administrator landing page showing aggregate counts for the
    most frequently monitored objects: total/active/inactive users, new-user
    acquisition over today/week/month windows, currently active sessions,
    total and active OAuth2 clients, and total RBAC roles. All counts are
    computed via their respective services (no direct SQL here); the rendered
    HTML is the admin shell's first screen after sign-in.

    **Required scope:** `users:read`

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/admin/
    ```
    """
    logger.debug("Admin dashboard requested")
    templates = get_templates()

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_users = await user_service.count(db)
    active_users = await user_service.count(db, is_active=True)
    new_users_today = await user_service.count(db, created_since=today_start)
    new_users_week = await user_service.count(db, created_since=week_ago)
    new_users_month = await user_service.count(db, created_since=month_ago)

    active_sessions = await session_service.count_active(db)

    total_clients = await oauth2_client_service.count(db)
    active_clients = await oauth2_client_service.count(db, is_active=True)

    total_roles = await role_service.count(db)

    stats = {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "new_users_today": new_users_today,
        "new_users_week": new_users_week,
        "new_users_month": new_users_month,
        "active_sessions": active_sessions,
        "total_clients": total_clients,
        "active_clients": active_clients,
        "total_roles": total_roles,
    }

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "active_section": "dashboard",
            "stats": stats,
            "permissions": permissions,
        },
    )
