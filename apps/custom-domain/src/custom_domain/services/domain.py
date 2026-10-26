# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Domain orchestration service.

Everything that needs privileges (nginx files, certificates) runs in the Celery
tasks, never here: this service is used by the API process.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.logging import get_logger
from custom_domain.models.client import AuthorizedClient
from custom_domain.models.domain import CustomDomain
from custom_domain.models.enums import DomainStatus
from custom_domain.services.dns import dns_service

logger = get_logger(__name__)


@dataclass
class VerificationResult:
    """Result of DNS verification."""

    success: bool
    verified_at: datetime | None = None
    error_message: str | None = None


class DomainService:
    """Service for orchestrating domain operations."""

    async def get_authorized_client(
        self,
        db: AsyncSession,
        client_id: str,
    ) -> AuthorizedClient | None:
        """Get an authorized client by client_id.

        Args:
            db: Database session
            client_id: OAuth2 client ID

        Returns:
            AuthorizedClient if found and active, None otherwise
        """
        result = await db.execute(
            select(AuthorizedClient).where(
                AuthorizedClient.client_id == client_id,
                AuthorizedClient.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def verify_dns(
        self,
        db: AsyncSession,
        domain: CustomDomain,
    ) -> VerificationResult:
        """Verify DNS configuration for a domain.

        Args:
            db: Database session
            domain: The CustomDomain to verify

        Returns:
            VerificationResult with verification status
        """
        logger.info("Verifying DNS for %s", domain.domain)

        # Update status to verifying
        domain.status = DomainStatus.DNS_VERIFYING
        domain.last_check_at = datetime.now(UTC)
        await db.commit()

        # Check CNAME
        result = await dns_service.check_cname(
            domain.domain,
            domain.cname_target,
        )

        if result.success:
            domain.status = DomainStatus.DNS_VERIFIED
            domain.dns_verified_at = datetime.now(UTC)
            domain.error_message = None
            await db.commit()

            logger.info("DNS verified for %s", domain.domain)
            return VerificationResult(
                success=True,
                verified_at=domain.dns_verified_at,
            )
        else:
            domain.error_message = result.error_message
            domain.retry_count += 1
            await db.commit()

            logger.warning(
                "DNS verification failed for %s: %s",
                domain.domain,
                result.error_message,
            )
            return VerificationResult(
                success=False,
                error_message=result.error_message,
            )

    def validate_domain_name(self, domain: str) -> tuple[bool, str | None]:
        """Validate a domain name.

        Args:
            domain: The domain name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        import re

        # Check length
        if len(domain) > 255:
            return False, "Domain name too long (max 255 characters)"

        # Check format
        pattern = r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$"
        if not re.match(pattern, domain):
            return False, "Invalid domain name format"

        return True, None


domain_service = DomainService()
