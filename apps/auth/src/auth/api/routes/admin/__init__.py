# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin HTML pages.

The legacy JSON routes that lived here (``clients.py``, ``jwks.py``,
``pats.py``, ``roles.py``, ``sessions.py``, ``tenants.py``, ``users.py``)
have been removed; ``/api/v1/`` is the canonical JSON layer for those
resources. Only the server-rendered HTML admin console remains here.
"""

from fastapi import APIRouter

from auth.api.routes.admin import (
    clients_pages,
    dashboard,
    jwks_pages,
    pats_pages,
    roles_pages,
    scopes_pages,
    sessions_pages,
    tenants_pages,
    users_pages,
)

# Pages router (requires session + scope-based authorization, redirects to login)
pages_router = APIRouter(prefix="/admin", tags=["admin-pages"])
pages_router.include_router(dashboard.router)
pages_router.include_router(jwks_pages.router)
pages_router.include_router(sessions_pages.router)
pages_router.include_router(users_pages.router)
pages_router.include_router(clients_pages.router)
pages_router.include_router(roles_pages.router)
pages_router.include_router(scopes_pages.router)
pages_router.include_router(tenants_pages.router)
pages_router.include_router(pats_pages.router)
