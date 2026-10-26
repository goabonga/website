# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Abstract base class for email providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class EmailResult:
    """Result of an email send operation."""

    success: bool
    error_message: str | None = None
    provider_message_id: str | None = None


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name.

        Returns:
            Provider name (e.g., 'brevo', 'sendgrid', 'ses', 'protonmail')
        """
        pass

    @abstractmethod
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
        """Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML content
            plain_body: Plain text content (optional)
            from_name: Sender name (optional, uses default)
            from_email: Sender email (optional, uses default)
            reply_to: Reply-to address (optional)
            email_id: Email record UUID for webhook signature (optional)
            metadata: Additional metadata (campaign_id, etc.) for webhooks (optional)

        Returns:
            EmailResult with success status and optional message ID
        """
        pass

    @property
    def is_configured(self) -> bool:
        """Check if the provider is properly configured.

        Returns:
            True if configured, False otherwise
        """
        return True
