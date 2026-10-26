# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Routes package for internal application."""

from internal.routes.analytics import router as analytics_router
from internal.routes.auth import router as auth_router

__all__ = [
    "analytics_router",
    "auth_router",
]
