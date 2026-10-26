# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""GitHub webhook proxy.

Receives GitHub webhook events and forwards them to the internal API.
Optional HMAC-SHA256 signature verification at gateway level.
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


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature.

    Args:
        payload: Raw request body.
        signature: X-Hub-Signature-256 header value.
        secret: Webhook secret.

    Returns:
        True if signature is valid.
    """
    if not signature:
        logger.warning("Missing signature in GitHub webhook request")
        return False

    try:
        if not signature.startswith("sha256="):
            return False

        expected_sig = signature[7:]

        computed_sig = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed_sig, expected_sig)

    except Exception as e:
        logger.error("Error verifying GitHub signature: %s", e)
        return False


def get_internal_client() -> httpx.AsyncClient:
    """Get HTTP client configured for GitHub internal API.

    Supports both Unix socket (preferred) and HTTP URL.
    """
    if settings.github_internal_api_socket:
        transport = httpx.AsyncHTTPTransport(uds=settings.github_internal_api_socket)
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")
    elif settings.github_internal_api_url:
        return httpx.AsyncClient(base_url=settings.github_internal_api_url)
    else:
        raise ValueError(
            "Neither github_internal_api_socket nor github_internal_api_url configured"
        )


@router.post("")
@router.post("/")
async def github_webhook(request: Request) -> Response:
    """Proxy GitHub webhook to internal API.

    Forwards the raw request body and GitHub headers
    to the internal API for processing.

    Returns:
        200 OK on success.
    """
    if not settings.github_internal_api_socket and not settings.github_internal_api_url:
        logger.warning("GitHub internal API not configured (no socket or URL)")
        return Response(status_code=503, content="Service unavailable")

    payload = await request.body()
    if not payload:
        return Response(status_code=200)

    # Verify signature if secret is configured
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.github_webhook_secret and not verify_github_signature(
        payload, signature, settings.github_webhook_secret
    ):
        logger.warning("Invalid GitHub webhook signature")
        return Response(status_code=401, content="Invalid signature")

    logger.info("Proxying GitHub webhook to internal API")

    # Forward with GitHub-specific headers
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    event_type = request.headers.get("X-GitHub-Event")
    if event_type:
        headers["X-GitHub-Event"] = event_type
    delivery_id = request.headers.get("X-GitHub-Delivery")
    if delivery_id:
        headers["X-GitHub-Delivery"] = delivery_id
    auth_header = await get_authorization_header(settings.github_internal_api_token)
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        async with get_internal_client() as client:
            response = await client.post(
                "/webhooks/github",
                content=payload,
                headers=headers,
                timeout=30.0,
            )

            logger.info(
                "GitHub internal API response | status=%d",
                response.status_code,
            )

            return Response(
                status_code=response.status_code,
                content=response.content,
            )

    except httpx.ConnectError as e:
        logger.error("Failed to connect to GitHub internal API: %s", e)
        return Response(status_code=502, content="Bad gateway")
    except Exception as e:
        logger.exception("Error proxying to GitHub internal API: %s", e)
        return Response(status_code=500, content="Internal server error")
