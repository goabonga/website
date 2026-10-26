# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Brevo webhook proxy.

Receives Brevo webhook events and forwards them to the internal API.
Optional HMAC signature verification at gateway level.
"""

import hashlib
import hmac

import httpx
from fastapi import APIRouter, Request, Response

from webhooks.auth import get_authorization_header
from webhooks.config import settings
from webhooks.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def verify_brevo_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify Brevo webhook signature.

    Brevo uses HMAC-SHA256 to sign webhook payloads.

    Args:
        payload: Raw request body.
        signature: Signature value from X-Sib-Webhook-Signature header.
        secret: Webhook secret from Brevo dashboard.

    Returns:
        True if signature is valid, False otherwise.
    """
    if not signature:
        logger.warning("Missing signature in Brevo webhook request")
        return False

    try:
        computed_sig = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed_sig, signature)

    except Exception as e:
        logger.error("Error verifying Brevo signature: %s", e)
        return False


def get_internal_client() -> httpx.AsyncClient:
    """Get HTTP client configured for Brevo internal API.

    Supports both Unix socket (preferred) and HTTP URL.
    """
    if settings.brevo_internal_api_socket:
        transport = httpx.AsyncHTTPTransport(uds=settings.brevo_internal_api_socket)
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")
    elif settings.brevo_internal_api_url:
        return httpx.AsyncClient(base_url=settings.brevo_internal_api_url)
    else:
        raise ValueError("Neither brevo_internal_api_socket nor brevo_internal_api_url configured")


@router.post("")
@router.post("/")
async def brevo_webhook(request: Request) -> Response:
    """Proxy Brevo webhook to internal API.

    Forwards the raw request body to the internal API for processing.

    Returns:
        200 OK on success.
    """
    if not settings.brevo_internal_api_socket and not settings.brevo_internal_api_url:
        logger.warning("Brevo internal API not configured (no socket or URL)")
        return Response(status_code=503, content="Service unavailable")

    payload = await request.body()
    if not payload:
        return Response(status_code=200)

    # Verify signature if secret is configured
    if settings.brevo_webhook_secret:
        signature = request.headers.get("X-Sib-Webhook-Signature", "")
        if not verify_brevo_signature(payload, signature, settings.brevo_webhook_secret):
            logger.warning("Invalid Brevo webhook signature")
            return Response(status_code=401, content="Invalid signature")

    logger.info("Proxying Brevo webhook to internal API")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth_header = await get_authorization_header(settings.brevo_internal_api_token)
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        async with get_internal_client() as client:
            response = await client.post(
                "/api/v1/webhooks/brevo",
                content=payload,
                headers=headers,
                timeout=30.0,
            )

            logger.info(
                "Brevo internal API response | status=%d",
                response.status_code,
            )

            return Response(
                status_code=response.status_code,
                content=response.content,
            )

    except httpx.ConnectError as e:
        logger.error("Failed to connect to Brevo internal API: %s", e)
        return Response(status_code=502, content="Bad gateway")
    except Exception as e:
        logger.exception("Error proxying to Brevo internal API: %s", e)
        return Response(status_code=500, content="Internal server error")
