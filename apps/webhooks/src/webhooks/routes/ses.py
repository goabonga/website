# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Amazon SES/SNS webhook proxy.

Receives SES webhook events via SNS and forwards them to the internal API.
The internal API handles SNS verification, subscription confirmation,
and event processing.
"""

import httpx
from fastapi import APIRouter, Request, Response

from webhooks.auth import get_authorization_header
from webhooks.config import settings
from webhooks.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def get_internal_client() -> httpx.AsyncClient:
    """Get HTTP client configured for SES internal API.

    Supports both Unix socket (preferred) and HTTP URL.
    """
    if settings.ses_internal_api_socket:
        transport = httpx.AsyncHTTPTransport(uds=settings.ses_internal_api_socket)
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")
    elif settings.ses_internal_api_url:
        return httpx.AsyncClient(base_url=settings.ses_internal_api_url)
    else:
        raise ValueError("Neither ses_internal_api_socket nor ses_internal_api_url configured")


@router.post("")
@router.post("/")
async def ses_webhook(request: Request) -> Response:
    """Proxy SES/SNS webhook to internal API.

    Forwards the raw SNS payload and headers to the internal API
    for verification and processing.

    Returns:
        200 OK on success.
    """
    if not settings.ses_internal_api_socket and not settings.ses_internal_api_url:
        logger.warning("SES internal API not configured (no socket or URL)")
        return Response(status_code=503, content="Service unavailable")

    payload = await request.body()
    if not payload:
        return Response(status_code=200)

    # Forward SNS-specific headers
    headers: dict[str, str] = {
        "Content-Type": request.headers.get("Content-Type", "text/plain"),
    }
    for header_name in (
        "x-amz-sns-message-type",
        "x-amz-sns-message-id",
        "x-amz-sns-topic-arn",
        "x-amz-sns-subscription-arn",
    ):
        value = request.headers.get(header_name)
        if value:
            headers[header_name] = value

    auth_header = await get_authorization_header(settings.ses_internal_api_token)
    if auth_header:
        headers["Authorization"] = auth_header

    logger.info("Proxying SES/SNS webhook to internal API")

    try:
        async with get_internal_client() as client:
            response = await client.post(
                "/webhooks/ses",
                content=payload,
                headers=headers,
                timeout=30.0,
            )

            logger.info(
                "SES internal API response | status=%d",
                response.status_code,
            )

            return Response(
                status_code=response.status_code,
                content=response.content,
            )

    except httpx.ConnectError as e:
        logger.error("Failed to connect to SES internal API: %s", e)
        return Response(status_code=502, content="Bad gateway")
    except Exception as e:
        logger.exception("Error proxying to SES internal API: %s", e)
        return Response(status_code=500, content="Internal server error")
