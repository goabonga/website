# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Stripe webhook proxy.

Receives Stripe webhooks and forwards them to the internal API.
The internal API handles signature verification.
"""

import httpx
from fastapi import APIRouter, Request, Response

from webhooks.auth import get_authorization_header
from webhooks.config import settings
from webhooks.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def get_internal_client() -> httpx.AsyncClient:
    """Get HTTP client configured for Stripe internal API.

    Supports both Unix socket (preferred) and HTTP URL.
    """
    if settings.stripe_internal_api_socket:
        transport = httpx.AsyncHTTPTransport(uds=settings.stripe_internal_api_socket)
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")
    elif settings.stripe_internal_api_url:
        return httpx.AsyncClient(base_url=settings.stripe_internal_api_url)
    else:
        raise ValueError(
            "Neither stripe_internal_api_socket nor stripe_internal_api_url configured"
        )


@router.post("")
@router.post("/")
async def stripe_webhook(request: Request) -> Response:
    """Proxy Stripe webhook to internal API.

    Forwards the raw request body and Stripe-Signature header
    to the internal API for verification and processing.

    Returns:
        200 OK on success.
    """
    if not settings.stripe_internal_api_socket and not settings.stripe_internal_api_url:
        logger.warning("Stripe internal API not configured (no socket or URL)")
        return Response(status_code=503, content="Service unavailable")

    payload = await request.body()
    if not payload:
        return Response(status_code=200)

    signature = request.headers.get("Stripe-Signature", "")

    logger.info("Proxying Stripe webhook to internal API")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Stripe-Signature": signature,
    }
    auth_header = await get_authorization_header(settings.stripe_internal_api_token)
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        async with get_internal_client() as client:
            response = await client.post(
                "/webhooks/stripe",
                content=payload,
                headers=headers,
                timeout=30.0,
            )

            logger.info(
                "Stripe internal API response | status=%d",
                response.status_code,
            )

            return Response(
                status_code=response.status_code,
                content=response.content,
            )

    except httpx.ConnectError as e:
        logger.error("Failed to connect to Stripe internal API: %s", e)
        return Response(status_code=502, content="Bad gateway")
    except Exception as e:
        logger.exception("Error proxying to Stripe internal API: %s", e)
        return Response(status_code=500, content="Internal server error")
