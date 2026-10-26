# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Synchronous HTTP client for Mailler API (for Celery tasks)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from internal.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of sending an email via Mailler API."""

    success: bool
    error_message: str | None = None
    provider_message_id: str | None = None
    email_id: str | None = None
    task_id: str | None = None


class SyncMaillerClient:
    """Synchronous HTTP client for Mailler API (for Celery tasks)."""

    def __init__(self) -> None:
        self._socket_path = settings.mailler_socket_path or ""
        # For socket connections, use http://localhost as base URL (routing via socket)
        if self._socket_path:
            self._base_url = "http://localhost"
        else:
            self._base_url = (
                settings.mailler_api_url.rstrip("/") if settings.mailler_api_url else ""
            )
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._tokens: dict[str, tuple[str, datetime]] = {}

    def _get_access_token(self, scope: str = "mailler:send") -> str:
        """Get access token using client credentials flow."""
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        with httpx.Client() as client:
            response = client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._tokens[scope] = (access_token, expires_at)
        return access_token

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        scope: str = "mailler:send",
    ) -> Any:
        """Make an authenticated request to the Mailler API."""
        if not self._base_url:
            logger.warning("mailler_api_url not configured, cannot send emails via Mailler")
            return {}

        try:
            token = self._get_access_token(scope=scope)
        except Exception as e:
            logger.error("Failed to get access token for Mailler API: %s", e)
            raise

        # Use Unix socket transport if configured
        transport = None
        if self._socket_path:
            transport = httpx.HTTPTransport(uds=self._socket_path)

        with httpx.Client(timeout=30.0, transport=transport) as client:
            response = client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    def get_providers(self) -> list[str]:
        """Get list of available email providers.

        Returns:
            List of provider names (e.g., ["brevo", "sendgrid", "ses"])
        """
        try:
            data = self._request(
                "GET",
                "/api/v1/providers",
                scope="mailler:read",
            )
            if not data:
                return []
            return data.get("providers", [])
        except Exception as e:
            logger.exception("Failed to get providers from Mailler API: %s", e)
            return []

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        plain_body: str | None,
        provider: str,
        from_name: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailResult:
        """Send an email via the Mailler API.

        Args:
            to: Recipient email address.
            subject: Email subject.
            html_body: HTML content.
            plain_body: Plain text content.
            provider: Provider name (brevo, sendgrid, ses, protonmail).
            from_name: Sender name (optional).
            from_email: Sender email (optional).
            reply_to: Reply-to address (optional).
            metadata: Additional metadata (optional).

        Returns:
            EmailResult with success status and details.
        """
        try:
            payload: dict[str, Any] = {
                "to_email": to,
                "subject": subject,
                "html_content": html_body,
                "provider": provider,
            }

            if plain_body:
                payload["text_content"] = plain_body
            if from_name:
                payload["from_name"] = from_name
            if from_email:
                payload["from_email"] = from_email
            if reply_to:
                payload["reply_to"] = reply_to
            if metadata:
                payload["metadata"] = metadata

            data = self._request(
                "POST",
                "/api/v1/send",
                json_data=payload,
                scope="mailler:send",
            )

            if not data:
                return EmailResult(
                    success=False,
                    error_message="Empty response from Mailler API",
                )

            return EmailResult(
                success=True,
                email_id=data.get("id"),
                task_id=data.get("task_id"),
            )

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("detail", str(e))
            except Exception:
                error_detail = str(e)

            logger.error(
                "Mailler API error: %s (status=%s)",
                error_detail,
                e.response.status_code,
            )
            return EmailResult(
                success=False,
                error_message=error_detail,
            )

        except Exception as e:
            logger.exception("Failed to send email via Mailler API: %s", e)
            return EmailResult(
                success=False,
                error_message=str(e),
            )


def get_sync_mailler_client() -> SyncMaillerClient:
    """Get a sync mailler client instance."""
    return SyncMaillerClient()
