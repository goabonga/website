# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""AWS SES email provider."""

from typing import Any

import boto3
from botocore.exceptions import ClientError

from mailler.config import settings
from mailler.logging import get_logger
from mailler.services.providers.base import EmailProvider, EmailResult

logger = get_logger(__name__)


class SESProvider(EmailProvider):
    """AWS Simple Email Service provider."""

    def __init__(
        self,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        default_from: str | None = None,
        default_from_name: str | None = None,
    ):
        """Initialize SES provider.

        Args:
            region: AWS region (defaults to settings)
            access_key: AWS access key (defaults to settings)
            secret_key: AWS secret key (defaults to settings)
            default_from: Default sender email (defaults to settings)
            default_from_name: Default sender name (defaults to settings)
        """
        self.region = region or settings.ses_region
        self.access_key = access_key or settings.ses_access_key
        self.secret_key = secret_key or settings.ses_secret_key
        self.default_from = default_from or settings.default_from
        self.default_from_name = default_from_name or settings.default_from_name
        self._client = None

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "ses"

    @property
    def is_configured(self) -> bool:
        """Check if SES is configured."""
        return bool(self.access_key and self.secret_key and self.region)

    def _get_client(self):
        """Get or create SES client."""
        if self._client is None:
            self._client = boto3.client(
                "ses",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        return self._client

    def _format_sender(self, name: str | None, email: str) -> str:
        """Format sender address with name."""
        if name:
            return f"{name} <{email}>"
        return email

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
        """Send email via AWS SES."""
        if not self.is_configured:
            return EmailResult(success=False, error_message="AWS SES credentials not configured")

        sender = self._format_sender(
            from_name or self.default_from_name,
            from_email or self.default_from,
        )

        body = {"Html": {"Data": html_body, "Charset": "UTF-8"}}
        if plain_body:
            body["Text"] = {"Data": plain_body, "Charset": "UTF-8"}

        try:
            client = self._get_client()
            kwargs = {
                "Source": sender,
                "Destination": {"ToAddresses": [to]},
                "Message": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body,
                },
            }

            if reply_to:
                kwargs["ReplyToAddresses"] = [reply_to]

            response = client.send_email(**kwargs)
            message_id = response.get("MessageId")

            logger.info(
                "Email sent via SES",
                extra={"to": to, "message_id": message_id},
            )
            return EmailResult(success=True, provider_message_id=message_id)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                "SES API error",
                extra={"error_code": error_code, "error": error_message},
            )
            return EmailResult(success=False, error_message=f"{error_code}: {error_message}")
        except Exception as e:
            logger.error("SES unexpected error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
