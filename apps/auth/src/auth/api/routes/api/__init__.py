# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 routes (Bearer token authentication, JSON only)."""

from fastapi import APIRouter

from auth.api.routes.api import clients, jwks, pats, roles, scopes, sessions, users
from auth.api.routes.api.me import router as me_router
from auth.api.routes.api.organisations import router as organisations_router

router = APIRouter(prefix="/api/v1", tags=["api-v1"])

router.include_router(me_router)
router.include_router(organisations_router)
router.include_router(users.router)
router.include_router(clients.router)
router.include_router(roles.router)
router.include_router(scopes.router)
router.include_router(sessions.router)
router.include_router(jwks.router)
router.include_router(pats.router)
