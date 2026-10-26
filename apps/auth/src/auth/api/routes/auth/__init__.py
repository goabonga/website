# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication routes."""

from fastapi import APIRouter

from auth.api.routes.auth import logout, register, verify

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(register.router)
router.include_router(verify.router)
router.include_router(logout.router)
