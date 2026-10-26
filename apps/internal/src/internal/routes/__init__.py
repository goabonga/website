# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Routes package for internal application."""

from internal.routes.admin import router as admin_router
from internal.routes.analytics import router as analytics_router
from internal.routes.auth import router as auth_router
from internal.routes.billing import router as billing_router
from internal.routes.team import router as team_router
from internal.routes.vpn import router as vpn_router

__all__ = [
    "admin_router",
    "analytics_router",
    "auth_router",
    "billing_router",
    "team_router",
    "vpn_router",
]
