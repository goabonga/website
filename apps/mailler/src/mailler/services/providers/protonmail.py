# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Protonmail SMTP Bridge provider."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from mailler.config import settings
from mailler.logging import get_logger
from mailler.services.providers.base import EmailProvider, EmailResult

logger = get_logger(__name__)


class ProtonmailProvider(EmailProvider):
    """Protonmail Bridge SMTP provider.

    Uses the local Protonmail Bridge SMTP server to send emails
    through a Protonmail account.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        default_from: str | None = None,
        default_from_name: str | None = None,
    ):
        """Initialize Protonmail provider.

        Args:
            host: SMTP host (defaults to settings)
            port: SMTP port (defaults to settings)
            username: SMTP username (defaults to settings)
            password: SMTP password (defaults to settings)
            default_from: Default sender email (defaults to settings)
            default_from_name: Default sender name (defaults to settings)
        """
        self.host = host or settings.protonmail_host
        self.port = port or settings.protonmail_port
        self.username = username or settings.protonmail_user
        self.password = password or settings.protonmail_password
        self.default_from = default_from or settings.default_from
        self.default_from_name = default_from_name or settings.default_from_name

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "protonmail"

    @property
    def is_configured(self) -> bool:
        """Check if Protonmail is configured."""
        return bool(self.host and self.port and self.username and self.password)

    def _format_address(self, name: str | None, email: str) -> str:
        """Format email address with name."""
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
        """Send email via Protonmail Bridge SMTP."""
        if not self.is_configured:
            return EmailResult(success=False, error_message="Protonmail SMTP not configured")

        sender_email = from_email or self.default_from
        sender_name = from_name or self.default_from_name

        # Create multipart message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._format_address(sender_name, sender_email)
        msg["To"] = to

        if reply_to:
            msg["Reply-To"] = reply_to

        # Attach plain text first (fallback), then HTML
        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(sender_email, [to], msg.as_string())

            logger.info(
                "Email sent via Protonmail",
                extra={"to": to},
            )
            return EmailResult(success=True)

        except smtplib.SMTPAuthenticationError as e:
            logger.error("Protonmail authentication error", extra={"error": str(e)})
            return EmailResult(success=False, error_message="SMTP authentication failed")
        except smtplib.SMTPRecipientsRefused as e:
            logger.error("Protonmail recipient refused", extra={"error": str(e)})
            return EmailResult(success=False, error_message="Recipient refused")
        except smtplib.SMTPException as e:
            logger.error("Protonmail SMTP error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
        except Exception as e:
            logger.error("Protonmail unexpected error", extra={"error": str(e)})
            return EmailResult(success=False, error_message=str(e))
