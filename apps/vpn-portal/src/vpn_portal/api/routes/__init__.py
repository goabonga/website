# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes package."""

from fastapi import APIRouter

from vpn_portal.api.routes import health

router = APIRouter()
router.include_router(health.router)
