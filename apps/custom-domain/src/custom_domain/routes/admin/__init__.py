# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin routes."""

from custom_domain.routes.admin.clients import router as clients_router
from custom_domain.routes.admin.templates import router as templates_router

__all__ = ["clients_router", "templates_router"]
