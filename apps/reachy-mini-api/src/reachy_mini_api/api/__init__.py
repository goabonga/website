# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes for Reachy Mini."""

from fastapi import APIRouter

from reachy_mini_api.api.reports import router as reports_router

router = APIRouter()

router.include_router(reports_router, prefix="/reports", tags=["reports"])
