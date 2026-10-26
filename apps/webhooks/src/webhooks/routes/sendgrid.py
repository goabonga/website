# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SendGrid webhook proxy.

Receives SendGrid webhook events and forwards them to the internal API.
Optional ECDSA signature verification at gateway level.
"""

import base64

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Request, Response

from webhooks.auth import get_authorization_header
from webhooks.config import settings
from webhooks.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def verify_sendgrid_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    verification_key: str,
) -> bool:
    """Verify SendGrid Event Webhook signature.

    SendGrid uses ECDSA with SHA256 to sign webhook payloads.

    Args:
        payload: Raw request body.
        signature: Base64-encoded signature from X-Twilio-Email-Event-Webhook-Signature header.
        timestamp: Timestamp from X-Twilio-Email-Event-Webhook-Timestamp header.
        verification_key: Public verification key from SendGrid dashboard (PEM format).

    Returns:
        True if signature is valid, False otherwise.
    """
    if not signature or not timestamp:
        logger.warning("Missing signature or timestamp in SendGrid webhook request")
        return False

    try:
        loaded_key = serialization.load_pem_public_key(verification_key.encode("utf-8"))
        if not isinstance(loaded_key, ec.EllipticCurvePublicKey):
            logger.error("SendGrid verification key is not an ECDSA key")
            return False
        public_key = loaded_key

        signed_payload = timestamp.encode("utf-8") + payload
        decoded_signature = base64.b64decode(signature)

        public_key.verify(
            decoded_signature,
            signed_payload,
            ec.ECDSA(hashes.SHA256()),
        )
        return True

    except InvalidSignature:
        logger.warning("Invalid SendGrid webhook signature")
        return False

    except Exception as e:
        logger.error("Error verifying SendGrid signature: %s", e)
        return False


def get_internal_client() -> httpx.AsyncClient:
    """Get HTTP client configured for SendGrid internal API.

    Supports both Unix socket (preferred) and HTTP URL.
    """
    if settings.sendgrid_internal_api_socket:
        transport = httpx.AsyncHTTPTransport(uds=settings.sendgrid_internal_api_socket)
        return httpx.AsyncClient(transport=transport, base_url="http://localhost")
    elif settings.sendgrid_internal_api_url:
        return httpx.AsyncClient(base_url=settings.sendgrid_internal_api_url)
    else:
        raise ValueError(
            "Neither sendgrid_internal_api_socket nor sendgrid_internal_api_url configured"
        )


@router.post("")
@router.post("/")
async def sendgrid_webhook(request: Request) -> Response:
    """Proxy SendGrid webhook to internal API.

    Forwards the raw request body and signature headers
    to the internal API for processing.

    Returns:
        200 OK on success.
    """
    if not settings.sendgrid_internal_api_socket and not settings.sendgrid_internal_api_url:
        logger.warning("SendGrid internal API not configured (no socket or URL)")
        return Response(status_code=503, content="Service unavailable")

    payload = await request.body()
    if not payload:
        return Response(status_code=200)

    # Verify signature if verification key is configured
    signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
    timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")

    if settings.sendgrid_webhook_verification_key and not verify_sendgrid_signature(
        payload, signature, timestamp, settings.sendgrid_webhook_verification_key
    ):
        logger.warning("Invalid SendGrid webhook signature")
        return Response(status_code=401, content="Invalid signature")

    logger.info("Proxying SendGrid webhook to internal API")

    # Forward with signature headers for internal API verification
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if signature:
        headers["X-Twilio-Email-Event-Webhook-Signature"] = signature
    if timestamp:
        headers["X-Twilio-Email-Event-Webhook-Timestamp"] = timestamp
    auth_header = await get_authorization_header(settings.sendgrid_internal_api_token)
    if auth_header:
        headers["Authorization"] = auth_header
    try:
        async with get_internal_client() as client:
            response = await client.post(
                "/webhooks/sendgrid",
                content=payload,
                headers=headers,
                timeout=30.0,
            )

            logger.info(
                "SendGrid internal API response | status=%d",
                response.status_code,
            )

            return Response(
                status_code=response.status_code,
                content=response.content,
            )

    except httpx.ConnectError as e:
        logger.error("Failed to connect to SendGrid internal API: %s", e)
        return Response(status_code=502, content="Bad gateway")
    except Exception as e:
        logger.exception("Error proxying to SendGrid internal API: %s", e)
        return Response(status_code=500, content="Internal server error")
