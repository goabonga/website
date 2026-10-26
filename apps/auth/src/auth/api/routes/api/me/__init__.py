# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /me router."""

from fastapi import APIRouter

from auth.api.routes.api.me import applications, mfa, password, pats, profile, sessions

router = APIRouter(prefix="/me", tags=["me"])

router.include_router(profile.router)
router.include_router(password.router)
router.include_router(sessions.router)
router.include_router(mfa.router)
router.include_router(pats.router)
router.include_router(applications.router)
