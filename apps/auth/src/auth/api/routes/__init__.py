# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from fastapi import APIRouter

from auth.api.routes import discovery, health, jwks

router = APIRouter()


router.include_router(health.router, tags=["health"])
router.include_router(discovery.router, tags=["oidc"])
router.include_router(jwks.router, tags=["oidc"])
