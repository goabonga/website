# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Web routes for HTML pages."""

from knowledge.routes.web.downloads import router as downloads_router
from knowledge.routes.web.home import router as home_router

__all__ = [
    "home_router",
    "downloads_router",
]
