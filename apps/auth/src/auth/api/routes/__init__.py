# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from fastapi import APIRouter

from auth.api.routes import discovery, health, jwks, userinfo
from auth.api.routes.auth import router as auth_router
from auth.api.routes.oauth2 import router as oauth2_router

router = APIRouter()


router.include_router(health.router, tags=["health"])
router.include_router(discovery.router, tags=["oidc"])
router.include_router(jwks.router, tags=["oidc"])
router.include_router(userinfo.router)
router.include_router(auth_router, include_in_schema=False)
router.include_router(oauth2_router)
