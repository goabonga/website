# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication routes."""

from fastapi import APIRouter

from auth.api.routes.auth import login, logout, mfa, password, register, settings, tokens, verify

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(register.router)
router.include_router(verify.router)
router.include_router(password.router)
router.include_router(login.router)
router.include_router(logout.router)
router.include_router(mfa.router)
router.include_router(settings.router)
router.include_router(tokens.router)
