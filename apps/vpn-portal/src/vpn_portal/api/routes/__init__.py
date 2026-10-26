# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes package."""

from fastapi import APIRouter

from vpn_portal.api.routes import health, vpn

router = APIRouter()
router.include_router(health.router)
router.include_router(vpn.router, prefix="/api/v1/vpn", tags=["vpn"])
