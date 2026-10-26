# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""DNS verification service."""

import socket
from dataclasses import dataclass

from custom_domain.config import settings
from custom_domain.logging import get_logger

logger = get_logger(__name__)

try:
    import dns.resolver

    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False
    logger.warning("dnspython not available, falling back to socket resolution")


@dataclass
class DNSCheckResult:
    """Result of a DNS check."""

    success: bool
    actual_value: str | None
    expected_value: str
    error_message: str | None = None


class DNSService:
    """Service for DNS verification."""

    def __init__(self):
        self._resolver = None
        if DNS_AVAILABLE:
            self._resolver = dns.resolver.Resolver()
            self._resolver.timeout = settings.dns_timeout_seconds
            self._resolver.lifetime = settings.dns_timeout_seconds

    async def check_cname(self, domain: str, expected_target: str) -> DNSCheckResult:
        """Check if a domain's CNAME record points to the expected target.

        Args:
            domain: The domain to check
            expected_target: The expected CNAME target

        Returns:
            DNSCheckResult with success status and actual value
        """
        expected = expected_target.rstrip(".").lower()

        try:
            if DNS_AVAILABLE and self._resolver:
                return await self._check_cname_dnspython(domain, expected)
            else:
                return await self._check_cname_socket(domain, expected)
        except Exception as e:
            logger.error("DNS check failed for %s: %s", domain, e)
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message=str(e),
            )

    async def _check_cname_dnspython(self, domain: str, expected: str) -> DNSCheckResult:
        """Check CNAME using dnspython."""
        assert self._resolver is not None  # Checked by caller
        try:
            answers = self._resolver.resolve(domain, "CNAME")
            for rdata in answers:
                actual = str(rdata.target).rstrip(".").lower()
                if actual == expected:
                    logger.info("CNAME verified for %s -> %s", domain, actual)
                    return DNSCheckResult(
                        success=True,
                        actual_value=actual,
                        expected_value=expected,
                    )

            # CNAME exists but doesn't match
            actual_cname: str | None = (
                str(answers[0].target).rstrip(".").lower() if answers else None
            )
            logger.warning(
                "CNAME mismatch for %s: expected %s, got %s",
                domain,
                expected,
                actual_cname,
            )
            return DNSCheckResult(
                success=False,
                actual_value=actual_cname,
                expected_value=expected,
                error_message=f"CNAME points to {actual_cname}, expected {expected}",
            )

        except dns.resolver.NXDOMAIN:
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message="Domain does not exist (NXDOMAIN)",
            )
        except dns.resolver.NoAnswer:
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message="No CNAME record found",
            )
        except dns.resolver.Timeout:
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message="DNS query timed out",
            )

    async def _check_cname_socket(self, domain: str, expected: str) -> DNSCheckResult:
        """Fallback CNAME check using socket (limited functionality)."""
        try:
            # Socket can't check CNAME directly, but we can verify resolution
            socket.gethostbyname(domain)
            logger.warning(
                "Socket fallback: domain %s resolves but CNAME cannot be verified",
                domain,
            )
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message="Cannot verify CNAME without dnspython",
            )
        except socket.gaierror as e:
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected,
                error_message=f"Domain resolution failed: {e}",
            )

    async def check_a_record(self, domain: str, expected_ip: str) -> DNSCheckResult:
        """Check if a domain's A record points to the expected IP.

        Args:
            domain: The domain to check
            expected_ip: The expected IP address

        Returns:
            DNSCheckResult with success status and actual value
        """
        try:
            if DNS_AVAILABLE and self._resolver:
                answers = self._resolver.resolve(domain, "A")
                for rdata in answers:
                    actual = str(rdata.address)
                    if actual == expected_ip:
                        return DNSCheckResult(
                            success=True,
                            actual_value=actual,
                            expected_value=expected_ip,
                        )
                actual_ip: str | None = str(answers[0].address) if answers else None
                return DNSCheckResult(
                    success=False,
                    actual_value=actual_ip,
                    expected_value=expected_ip,
                    error_message=f"A record points to {actual_ip}, expected {expected_ip}",
                )
            else:
                # Fallback to socket
                actual = socket.gethostbyname(domain)
                success = actual == expected_ip
                return DNSCheckResult(
                    success=success,
                    actual_value=actual,
                    expected_value=expected_ip,
                    error_message=None if success else f"A record points to {actual}",
                )
        except Exception as e:
            return DNSCheckResult(
                success=False,
                actual_value=None,
                expected_value=expected_ip,
                error_message=str(e),
            )


dns_service = DNSService()
