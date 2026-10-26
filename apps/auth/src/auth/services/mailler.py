# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Mailler service client for sending emails via the mailler microservice."""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import httpx

from auth.config import settings

logger = logging.getLogger(__name__)


class MaillerClient:
    """HTTP client for the mailler service.

    Supports both TCP/HTTP and Unix socket connections.
    """

    def __init__(self) -> None:
        """Initialize the mailler client."""
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    @contextmanager
    def _get_http_client(self, timeout: float = 30.0) -> Generator[httpx.Client, None, None]:
        """Create an HTTP client with Unix socket support if configured.

        Args:
            timeout: Request timeout in seconds.

        Yields:
            Configured httpx.Client instance.
        """
        if settings.mailler_unix_socket:
            # Use Unix socket transport
            transport = httpx.HTTPTransport(uds=settings.mailler_unix_socket)
            with httpx.Client(transport=transport, timeout=timeout) as client:
                yield client
        else:
            # Use standard TCP transport
            with httpx.Client(timeout=timeout) as client:
                yield client

    def _get_access_token(self) -> str:
        """Get a valid access token for the mailler service.

        Uses client credentials flow to obtain a token from the auth service.

        Returns:
            Access token string.

        Raises:
            Exception: If token acquisition fails.
        """
        # Check if we have a valid cached token
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        logger.info("Obtaining access token for mailler service")

        # Use client credentials flow to get a token from the auth service
        # The auth service is its own OIDC provider
        auth_url = settings.mailler_auth_url or settings.issuer
        if not auth_url:
            raise ValueError(
                "MAILLER_AUTH_URL or ISSUER must be configured for mailler integration"
            )

        token_url = f"{auth_url.rstrip('/')}/oauth2/token"

        try:
            # Token endpoint uses standard HTTP (not Unix socket)
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.mailler_client_id,
                        "client_secret": settings.mailler_client_secret,
                        "scope": "mailler:send",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if response.status_code != 200:
                    logger.error(
                        f"Failed to get mailler token: {response.status_code} - {response.text}"
                    )
                    raise Exception(f"Token acquisition failed: {response.status_code}")

                token_data = response.json()
                self._access_token = token_data["access_token"]
                # Cache token with some buffer before expiration
                expires_in = token_data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in

                logger.info("Successfully obtained mailler access token")
                return self._access_token

        except httpx.RequestError as e:
            logger.error(f"HTTP error getting mailler token: {e}")
            raise

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        to_name: str | None = None,
        reply_to: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an email via the mailler service.

        Args:
            to_email: Recipient email address.
            subject: Email subject.
            html_content: HTML body content.
            text_content: Plain text content (optional).
            from_email: Sender email (optional, uses default).
            from_name: Sender name (optional).
            to_name: Recipient name (optional).
            reply_to: Reply-to address (optional).
            provider: Email provider (optional, uses default).
            metadata: Custom metadata (optional).

        Returns:
            Response dict with id, status, message, and task_id.

        Raises:
            Exception: If the request fails.
        """
        if not settings.mailler_url:
            raise ValueError("MAILLER_URL is not configured")

        access_token = self._get_access_token()

        send_url = f"{settings.mailler_url.rstrip('/')}/api/v1/send"

        payload: dict[str, Any] = {
            "to_email": to_email,
            "subject": subject,
            "html_content": html_content,
            "provider": provider or settings.mailler_provider,
        }

        if text_content:
            payload["text_content"] = text_content
        if from_email:
            payload["from_email"] = from_email
        if from_name:
            payload["from_name"] = from_name
        if to_name:
            payload["to_name"] = to_name
        if reply_to:
            payload["reply_to"] = reply_to
        if metadata:
            payload["metadata"] = metadata

        if settings.mailler_unix_socket:
            logger.info(
                f"Sending email to {to_email} via mailler Unix socket ({payload['provider']})"
            )
        else:
            logger.info(f"Sending email to {to_email} via mailler ({payload['provider']})")

        try:
            with self._get_http_client() as client:
                response = client.post(
                    send_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code not in (200, 201, 202):
                    logger.error(f"Mailler send failed: {response.status_code} - {response.text}")
                    raise Exception(f"Mailler send failed: {response.status_code}")

                result = response.json()
                logger.info(f"Email queued via mailler: {result.get('id')}")
                return result

        except httpx.RequestError as e:
            logger.error(f"HTTP error sending email via mailler: {e}")
            raise


# Global client instance
_mailler_client: MaillerClient | None = None


def get_mailler_client() -> MaillerClient:
    """Get or create the global mailler client instance.

    Returns:
        MaillerClient instance.
    """
    global _mailler_client
    if _mailler_client is None:
        _mailler_client = MaillerClient()
    return _mailler_client
