# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Providers route for listing available email providers."""

from fastapi import APIRouter, Depends

from mailler.auth import AuthContext, require_scopes
from mailler.logging import get_logger
from mailler.services.providers.factory import get_available_providers

logger = get_logger(__name__)

router = APIRouter(tags=["Providers"])


@router.get("/providers")
async def list_providers(
    auth: AuthContext = Depends(require_scopes("mailler:read")),
) -> dict:
    """List available (configured) email providers.

    Returns:
        Dictionary with list of provider names
    """
    providers = get_available_providers()

    logger.info(
        "Providers list requested",
        extra={
            "user_id": str(auth.user.id) if auth.user.id else None,
            "providers_count": len(providers),
        },
    )

    return {
        "providers": providers,
    }
