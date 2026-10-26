# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Federation routes for external identity providers."""

from fastapi import APIRouter

from auth.api.routes.federation.callback import router as callback_router
from auth.api.routes.federation.providers import router as providers_router

router = APIRouter(prefix="/federation", tags=["federation"])

router.include_router(providers_router)
router.include_router(callback_router)
