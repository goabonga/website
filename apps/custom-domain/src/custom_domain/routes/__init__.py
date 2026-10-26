# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from custom_domain.routes.admin import clients_router, templates_router
from custom_domain.routes.domains import router as domains_router
from custom_domain.routes.events import router as events_router
from custom_domain.routes.health import router as health_router

__all__ = [
    "clients_router",
    "domains_router",
    "events_router",
    "health_router",
    "templates_router",
]
