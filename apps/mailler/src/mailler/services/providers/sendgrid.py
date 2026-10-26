# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SendGrid email provider."""

from typing import Any

import httpx

from mailler.config import settings
from mailler.logging import get_logger
from mailler.services.providers.base import EmailProvider, EmailResult

logger = get_logger(__name__)


class SendGridProvider(EmailProvider):
    """SendGrid email provider using their API."""

    API_URL = "https://api.sendgrid.com/v3/mail/send"

    def __init__(
        self,
        api_key: str | None = None,
        default_from: str | None = None,
        default_from_name: str | None = None,
    ):
        """Initialize SendGrid provider.

        Args:
            api_key: SendGrid API key (defaults to settings)
            default_from: Default sender email (defaults to settings)
            default_from_name: Default sender name (defaults to settings)
        """
        self.api_key = api_key or settings.sendgrid_api_key
        self.default_from = default_from or settings.default_from
        self.default_from_name = default_from_name or settings.default_from_name

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "sendgrid"

    @property
    def is_configured(self) -> bool:
        """Check if SendGrid is configured."""
        return bool(self.api_key)

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        plain_body: str | None = None,
        from_name: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
        email_id: str | None = None,  # noqa: ARG002
        metadata: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> EmailResult:
        """Send email via SendGrid API."""
        if not self.is_configured:
            return EmailResult(success=False, error_message="SendGrid API key not configured")

        content = [{"type": "text/html", "value": html_body}]
        if plain_body:
            content.insert(0, {"type": "text/plain", "value": plain_body})

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {
                "email": from_email or self.default_from,
                "name": from_name or self.default_from_name,
            },
            "subject": subject,
            "content": content,
        }

        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.API_URL, json=payload, headers=headers)

            if response.status_code == 202:
                # SendGrid returns message ID in X-Message-Id header
                message_id = response.headers.get("X-Message-Id")
                logger.info(
                    "Email sent via SendGrid",
                    extra={"to": to, "message_id": message_id},
                )
                return EmailResult(success=True, provider_message_id=message_id)
            else:
                error_data = response.json() if response.content else {}
                errors = error_data.get("errors", [])
                error_message = (
                    errors[0].get("message") if errors else f"HTTP {response.status_code}"
                )
                logger.error(
                    "SendGrid API error",
                    extra={"status": response.status_code, "error": error_message},
                )
                return EmailResult(success=False, error_message=error_message)

        except httpx.RequestError as e:
            logger.error("SendGrid request error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
        except Exception as e:
            logger.error("SendGrid unexpected error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
