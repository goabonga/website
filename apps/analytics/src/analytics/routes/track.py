# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Campaign link tracking endpoint."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.database import get_db
from analytics.logging import get_logger, set_request_context
from analytics.services.collector import collector_service, get_client_ip

logger = get_logger(__name__)

router = APIRouter(tags=["track"])


@router.get("/t/{tracking_key}")
async def track_link(
    tracking_key: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    url: Annotated[str | None, Query(description="Override destination URL")] = None,
) -> RedirectResponse:
    """Track campaign link click and redirect.

    This endpoint is used for tracking clicks on links in emails or marketing materials.
    It records the click and redirects to the destination URL.

    Usage:
        https://ua.goabonga.com/t/{tracking_key}
        https://ua.goabonga.com/t/{tracking_key}?url=https://example.com

    The destination URL can be:
    1. Stored in the campaign (default)
    2. Provided via the 'url' query parameter (override)
    """
    client_ip = get_client_ip(request)
    set_request_context(session_id=tracking_key, client_ip=client_ip)

    # Track the click
    campaign = await collector_service.track_campaign_click(
        db=db,
        tracking_key=tracking_key,
        request=request,
    )

    # Determine destination URL
    if url:
        # Use provided URL
        destination = url
    elif campaign and campaign.destination_url:
        # Use campaign's stored URL
        destination = campaign.destination_url
    else:
        # Fallback to homepage
        destination = "https://goabonga.com"
        logger.warning(f"No destination URL for tracking key: {tracking_key}")

    # Preserve UTM parameters from the original request
    utm_params = {}
    for key in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]:
        value = request.query_params.get(key)
        if value:
            utm_params[key] = value

    # Add tracking key as utm_content if not already set
    if "utm_content" not in utm_params and campaign:
        utm_params["utm_content"] = tracking_key

    # Append UTM parameters to destination
    if utm_params:
        separator = "&" if "?" in destination else "?"
        destination = f"{destination}{separator}{urlencode(utm_params)}"

    logger.info(f"Redirecting {tracking_key} to {destination}")

    return RedirectResponse(
        url=destination,
        status_code=302,  # Temporary redirect (allows tracking each click)
    )
