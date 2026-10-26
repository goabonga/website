# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from fastapi import APIRouter

from auth.api.routes import health

router = APIRouter()


router.include_router(health.router, tags=["health"])
