# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JSON API routes."""

from fastapi import APIRouter

from apt_server.routes.api.packages import router as packages_router
from apt_server.routes.api.reindex import router as reindex_router

router = APIRouter(prefix="/api")
router.include_router(packages_router)
router.include_router(reindex_router)
