# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/domain.py."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_domain.models.enums import DomainStatus
from custom_domain.services.domain import (
    VerificationResult,
    domain_service,
)


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = VerificationResult(
            success=True,
            verified_at=datetime.now(UTC),
        )
        assert result.success is True
        assert result.verified_at is not None

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = VerificationResult(
            success=False,
            error_message="CNAME not found",
        )
        assert result.success is False
        assert result.error_message is not None


class TestDomainService:
    """Tests for DomainService."""

    @pytest.mark.asyncio
    async def test_get_authorized_client(self):
        """Test getting an authorized client."""
        mock_client = MagicMock()
        mock_client.client_id = "test-client"
        mock_client.is_active = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = domain_service
        client = await service.get_authorized_client(mock_db, "test-client")

        assert client is not None
        assert client.client_id == "test-client"

    @pytest.mark.asyncio
    async def test_get_authorized_client_not_found(self):
        """Test getting non-existent client."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = domain_service
        client = await service.get_authorized_client(mock_db, "nonexistent")
        assert client is None

    @pytest.mark.asyncio
    async def test_verify_dns_success(self):
        """Test successful DNS verification."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        mock_db = AsyncMock()

        service = domain_service

        with patch("custom_domain.services.domain.dns_service") as mock_dns:
            mock_result = MagicMock()
            mock_result.success = True
            mock_dns.check_cname = AsyncMock(return_value=mock_result)

            result = await service.verify_dns(mock_db, mock_domain)

            assert result.success is True
            assert mock_domain.status == DomainStatus.DNS_VERIFIED

    @pytest.mark.asyncio
    async def test_verify_dns_failure(self):
        """Test DNS verification failure."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.retry_count = 0

        mock_db = AsyncMock()

        service = domain_service

        with patch("custom_domain.services.domain.dns_service") as mock_dns:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.error_message = "CNAME not found"
            mock_dns.check_cname = AsyncMock(return_value=mock_result)

            result = await service.verify_dns(mock_db, mock_domain)

            assert result.success is False
            assert mock_domain.retry_count > 0

    def test_validate_domain_name_valid(self):
        """Test validating a valid domain name."""
        service = domain_service
        is_valid, error = service.validate_domain_name("test.example.com")
        assert is_valid is True
        assert error is None

    def test_validate_domain_name_invalid_format(self):
        """Test validating an invalid domain format."""
        service = domain_service
        is_valid, error = service.validate_domain_name("invalid")
        assert is_valid is False
        assert error is not None

    def test_validate_domain_name_too_long(self):
        """Test validating a domain that's too long."""
        service = domain_service
        long_domain = "a" * 256 + ".com"
        is_valid, error = service.validate_domain_name(long_domain)
        assert is_valid is False
        assert "too long" in error.lower()

    def test_validate_domain_name_hyphen_start(self):
        """Test validating domain starting with hyphen."""
        service = domain_service
        is_valid, error = service.validate_domain_name("-test.example.com")
        assert is_valid is False
