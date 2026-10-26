# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from fastapi import APIRouter

from auth.api.routes import discovery, health, jwks, me_legacy, userinfo
from auth.api.routes.api import router as api_router
from auth.api.routes.auth import router as auth_router
from auth.api.routes.federation import router as federation_router
from auth.api.routes.oauth2 import router as oauth2_router

router = APIRouter()


router.include_router(health.router, tags=["health"])
router.include_router(discovery.router, tags=["oidc"])
router.include_router(jwks.router, tags=["oidc"])
router.include_router(userinfo.router)
router.include_router(auth_router, include_in_schema=False)
router.include_router(oauth2_router)
router.include_router(federation_router, include_in_schema=False)
router.include_router(
    me_legacy.router,
    prefix="/api",
    tags=["api"],
    include_in_schema=False,
)  # Legacy /api/me/*
router.include_router(api_router)  # REST API at /api/v1/*
