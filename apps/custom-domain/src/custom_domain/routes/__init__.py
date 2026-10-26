# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from custom_domain.routes.admin import templates_router
from custom_domain.routes.health import router as health_router

__all__ = [
    "health_router",
    "templates_router",
]
