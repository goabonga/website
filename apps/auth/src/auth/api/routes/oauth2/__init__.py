# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 routes."""

from fastapi import APIRouter

from auth.api.routes.oauth2 import authorize, device, introspect, par, revoke, token

router = APIRouter(prefix="/oauth2", tags=["oauth2"])

router.include_router(authorize.router)
router.include_router(token.router)
router.include_router(device.router)
router.include_router(par.router)
router.include_router(revoke.router)
router.include_router(introspect.router)
