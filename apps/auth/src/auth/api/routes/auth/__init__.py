# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication routes."""

from fastapi import APIRouter

from auth.api.routes.auth import register, verify

router = APIRouter(prefix="/auth", tags=["auth"])

router.include_router(register.router)
router.include_router(verify.router)
