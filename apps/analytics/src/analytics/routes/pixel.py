# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tracking pixel endpoint for email campaigns."""

import base64
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.config import settings
from analytics.database import get_db
from analytics.logging import get_logger, set_request_context
from analytics.services.collector import collector_service, get_client_ip

logger = get_logger(__name__)

router = APIRouter(tags=["pixel"])

# 1x1 transparent GIF (43 bytes)
TRANSPARENT_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@router.get("/p/{pixel_key}.gif")
async def track_pixel(
    pixel_key: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Track email open via tracking pixel.

    This endpoint is called when an email client loads the embedded image.
    It records the open event and returns a 1x1 transparent GIF.

    Usage in email HTML:
        <img src="https://ua.goabonga.com/p/{pixel_key}.gif" width="1" height="1" />
    """
    client_ip = get_client_ip(request)
    set_request_context(session_id=pixel_key, client_ip=client_ip)

    # Track the pixel open
    pixel = await collector_service.track_pixel_open(
        db=db,
        pixel_key=pixel_key,
        request=request,
    )

    if pixel:
        logger.info(f"Pixel opened: {pixel_key}")
    else:
        logger.warning(f"Unknown pixel requested: {pixel_key}")

    # Always return the GIF (don't reveal if pixel exists or not)
    return Response(
        content=TRANSPARENT_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": settings.pixel_cache_control,
            "Pragma": "no-cache",
            "Expires": "0",
            # Prevent email clients from caching
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/p/{pixel_key}")
async def track_pixel_no_extension(
    pixel_key: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Track pixel without .gif extension (fallback)."""
    return await track_pixel(pixel_key, request, db)
