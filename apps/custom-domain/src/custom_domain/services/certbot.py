# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Certbot SSL certificate service."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from custom_domain.config import settings
from custom_domain.logging import get_logger
from custom_domain.privileged_helper import EXIT_NOT_FOUND
from custom_domain.services.privileged import run_privileged

logger = get_logger(__name__)


@dataclass
class CertbotResult:
    """Result of a certbot operation."""

    success: bool
    error_message: str | None = None
    expires_at: datetime | None = None


@dataclass
class CertificateInfo:
    """Information about an SSL certificate."""

    domain: str
    issued_at: datetime | None
    expires_at: datetime
    days_until_expiry: int


class CertbotService:
    """Service for managing SSL certificates via certbot.

    certbot and openssl run through the privileged helper (see
    :mod:`custom_domain.services.privileged`): the account of the service can not
    read the certificate directory nor run certbot itself.
    """

    @property
    def enabled(self) -> bool:
        """Whether certificates are requested at all (``CERTBOT_ENABLED``)."""
        return settings.certbot_enabled

    async def provision_certificate(self, domain: str) -> CertbotResult:
        """Provision an SSL certificate via Let's Encrypt.

        The webroot and the notification e-mail come from ``CERTBOT_WEBROOT`` and
        ``CERTBOT_EMAIL``; they are fixed by the sudoers rule, not by the caller.

        Args:
            domain: The domain to provision a certificate for

        Returns:
            CertbotResult with success status
        """
        if not self.enabled:
            logger.info("Certbot disabled, skipping certificate provisioning")
            return CertbotResult(
                success=True,
                error_message="Certbot disabled",
            )

        logger.info("Running certbot for %s", domain)

        try:
            result = await run_privileged("certbot-issue", domain)

            if not result.ok:
                error = result.stderr or "Unknown error"
                logger.error(
                    "Certbot failed for %s: %s",
                    domain,
                    error,
                )

                # Check for rate limiting
                if "rate limit" in error.lower():
                    return CertbotResult(
                        success=False,
                        error_message="Let's Encrypt rate limit exceeded. Try again later.",
                    )

                # Check for challenge failure
                if "challenge failed" in error.lower() or "unauthorized" in error.lower():
                    return CertbotResult(
                        success=False,
                        error_message="ACME challenge failed. Verify DNS configuration.",
                    )

                return CertbotResult(
                    success=False,
                    error_message=error[:500],
                )

            # Get certificate expiry
            cert_info = await self.check_certificate(domain)
            expires_at = cert_info.expires_at if cert_info else None

            logger.info(
                "Certificate provisioned for %s, expires at %s",
                domain,
                expires_at,
            )
            return CertbotResult(
                success=True,
                expires_at=expires_at,
            )

        except Exception as e:
            logger.exception("Certbot exception for %s", domain)
            return CertbotResult(
                success=False,
                error_message=str(e),
            )

    async def check_certificate(self, domain: str) -> CertificateInfo | None:
        """Check the status of an existing certificate.

        Args:
            domain: The domain to check

        Returns:
            CertificateInfo if certificate exists, None otherwise
        """
        try:
            result = await run_privileged("cert-dates", domain)

            if result.returncode == EXIT_NOT_FOUND or not result.ok:
                return None

            output = result.stdout

            # Parse dates
            not_after_match = re.search(r"notAfter=(.+)", output)
            not_before_match = re.search(r"notBefore=(.+)", output)

            if not not_after_match:
                return None

            # Parse the date format: "Jan 15 10:30:00 2024 GMT"
            expires_at = datetime.strptime(
                not_after_match.group(1).strip(),
                "%b %d %H:%M:%S %Y %Z",
            )

            issued_at = None
            if not_before_match:
                issued_at = datetime.strptime(
                    not_before_match.group(1).strip(),
                    "%b %d %H:%M:%S %Y %Z",
                )

            days_until_expiry = (expires_at - datetime.now(UTC).replace(tzinfo=None)).days

            return CertificateInfo(
                domain=domain,
                issued_at=issued_at,
                expires_at=expires_at,
                days_until_expiry=days_until_expiry,
            )

        except Exception as e:
            logger.warning("Failed to check certificate for %s: %s", domain, e)
            return None

    async def renew_certificate(self, domain: str) -> CertbotResult:
        """Renew an existing certificate.

        Args:
            domain: The domain to renew

        Returns:
            CertbotResult with success status
        """
        if not self.enabled:
            return CertbotResult(
                success=True,
                error_message="Certbot disabled",
            )

        logger.info("Renewing certificate for %s", domain)

        try:
            result = await run_privileged("certbot-renew", domain)

            if not result.ok:
                error = result.stderr or "Unknown error"
                logger.error("Certificate renewal failed for %s: %s", domain, error)
                return CertbotResult(
                    success=False,
                    error_message=error[:500],
                )

            cert_info = await self.check_certificate(domain)
            return CertbotResult(
                success=True,
                expires_at=cert_info.expires_at if cert_info else None,
            )

        except Exception as e:
            logger.exception("Certificate renewal exception for %s", domain)
            return CertbotResult(
                success=False,
                error_message=str(e),
            )

    async def revoke_certificate(self, domain: str) -> CertbotResult:
        """Revoke and delete a certificate.

        Args:
            domain: The domain whose certificate to revoke

        Returns:
            CertbotResult with success status; a domain without a certificate
            succeeds with an explanatory message
        """
        if not self.enabled:
            return CertbotResult(success=True)

        logger.info("Revoking certificate for %s", domain)

        try:
            result = await run_privileged("certbot-revoke", domain)

            if not result.ok:
                error = result.stderr or "Unknown error"
                logger.error("Certificate revocation failed for %s: %s", domain, error)
                return CertbotResult(
                    success=False,
                    error_message=error[:500],
                )

            if "certificate absent" in result.stdout:
                return CertbotResult(
                    success=True,
                    error_message="Certificate does not exist",
                )

            return CertbotResult(success=True)

        except Exception as e:
            logger.exception("Certificate revocation exception for %s", domain)
            return CertbotResult(
                success=False,
                error_message=str(e),
            )


certbot_service = CertbotService()
