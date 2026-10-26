# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Brevo (Sendinblue) email provider."""

from typing import Any

import httpx

from mailler.config import settings
from mailler.logging import get_logger
from mailler.services.providers.base import EmailProvider, EmailResult
from mailler.services.webhook_signature import build_mailin_custom

logger = get_logger(__name__)


class BrevoProvider(EmailProvider):
    """Brevo (Sendinblue) email provider using their API."""

    API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(
        self,
        api_key: str | None = None,
        default_from: str | None = None,
        default_from_name: str | None = None,
    ):
        """Initialize Brevo provider.

        Args:
            api_key: Brevo API key (defaults to settings)
            default_from: Default sender email (defaults to settings)
            default_from_name: Default sender name (defaults to settings)
        """
        self.api_key = api_key or settings.brevo_api_key
        self.default_from = default_from or settings.default_from
        self.default_from_name = default_from_name or settings.default_from_name

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "brevo"

    @property
    def is_configured(self) -> bool:
        """Check if Brevo is configured."""
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
        email_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailResult:
        """Send email via Brevo API."""
        if not self.is_configured:
            return EmailResult(success=False, error_message="Brevo API key not configured")

        payload = {
            "sender": {
                "name": from_name or self.default_from_name,
                "email": from_email or self.default_from,
            },
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html_body,
        }

        if plain_body:
            payload["textContent"] = plain_body

        if reply_to:
            payload["replyTo"] = {"email": reply_to}

        # Add X-Mailin-custom header with HMAC signature for webhook verification
        if email_id:
            # Extract campaign_id from metadata if present
            extra_data = {}
            if metadata and metadata.get("campaign_id"):
                extra_data["campaign_id"] = str(metadata["campaign_id"])

            mailin_custom = build_mailin_custom(
                email_id, to, extra=extra_data if extra_data else None
            )
            payload["headers"] = {"X-Mailin-custom": mailin_custom}
            logger.debug(
                "Brevo email with webhook signature",
                extra={
                    "email_id": email_id,
                    "to": to,
                    "campaign_id": extra_data.get("campaign_id"),
                    "x_mailin_custom": mailin_custom,
                },
            )

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.api_key,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.API_URL, json=payload, headers=headers)

            if response.status_code == 201:
                data = response.json()
                message_id = data.get("messageId")
                logger.info(
                    "Email sent via Brevo",
                    extra={"to": to, "message_id": message_id},
                )
                return EmailResult(success=True, provider_message_id=message_id)
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get("message", f"HTTP {response.status_code}")
                logger.error(
                    "Brevo API error",
                    extra={"status": response.status_code, "error": error_message},
                )
                return EmailResult(success=False, error_message=error_message)

        except httpx.RequestError as e:
            logger.error("Brevo request error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
        except Exception as e:
            logger.error("Brevo unexpected error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))

    async def unblock_contact(self, email: str) -> dict[str, Any]:
        """Unblock a contact in Brevo.

        Removes the email from Brevo's blacklist (soft bounces only).
        Hard bounces and spam complaints cannot be unblocked.

        Args:
            email: Email address to unblock

        Returns:
            Dict with success status and optional error message

        Example:
            {"success": True, "message": "Contact unblocked"}
            {"success": False, "error": "Contact not found"}
        """
        if not self.is_configured:
            return {"success": False, "error": "Brevo API key not configured"}

        url = f"https://api.brevo.com/v3/contacts/{email}/unblock"
        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    "Contact unblocked in Brevo",
                    extra={"email": email, "response": data},
                )
                return {
                    "success": True,
                    "message": data.get("message", "Contact unblocked"),
                }
            elif response.status_code == 404:
                logger.warning(
                    "Contact not found in Brevo blocklist",
                    extra={"email": email, "status": response.status_code},
                )
                # Not an error - contact may not be blocked
                return {"success": True, "message": "Contact not in blocklist"}
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get("message", f"HTTP {response.status_code}")
                logger.error(
                    "Brevo unblock API error",
                    extra={
                        "email": email,
                        "status": response.status_code,
                        "error": error_message,
                    },
                )
                return {"success": False, "error": error_message}

        except httpx.RequestError as e:
            logger.error("Brevo unblock request error", extra={"email": email, "error": str(e)})
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(
                "Brevo unblock unexpected error",
                extra={"email": email, "error": str(e)},
            )
            return {"success": False, "error": str(e)}

    async def get_contact_status(self, email: str) -> dict[str, Any]:
        """Get contact status from Brevo.

        Args:
            email: Email address to check

        Returns:
            Dict with contact status information
        """
        if not self.is_configured:
            return {"success": False, "error": "Brevo API key not configured"}

        url = f"https://api.brevo.com/v3/contacts/{email}"
        headers = {
            "accept": "application/json",
            "api-key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "email": data.get("email"),
                    "email_blacklisted": data.get("emailBlacklisted", False),
                    "sms_blacklisted": data.get("smsBlacklisted", False),
                }
            elif response.status_code == 404:
                return {"success": False, "error": "Contact not found in Brevo"}
            else:
                error_data = response.json() if response.content else {}
                error_message = error_data.get("message", f"HTTP {response.status_code}")
                return {"success": False, "error": error_message}

        except Exception as e:
            logger.error("Brevo get contact error", extra={"email": email, "error": str(e)})
            return {"success": False, "error": str(e)}
