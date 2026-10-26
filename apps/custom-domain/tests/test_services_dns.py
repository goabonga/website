# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/dns.py."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from custom_domain.services.dns import DNSCheckResult, DNSService


class TestDNSImportFallback:
    """Tests for DNS module import fallback when dnspython is not available."""

    def test_dns_module_import_fallback(self):
        """Test that DNS module falls back gracefully when dnspython is not available."""
        import builtins

        # Save original modules
        dns_module = sys.modules.get("dns")
        dns_resolver_module = sys.modules.get("dns.resolver")
        app_dns_module = sys.modules.get("custom_domain.services.dns")

        try:
            # Remove dns modules from sys.modules
            if "dns" in sys.modules:
                del sys.modules["dns"]
            if "dns.resolver" in sys.modules:
                del sys.modules["dns.resolver"]
            if "custom_domain.services.dns" in sys.modules:
                del sys.modules["custom_domain.services.dns"]

            # Create a custom import that raises ImportError for dns.resolver
            original_import = builtins.__import__

            def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "dns.resolver" or name == "dns":
                    raise ImportError("No module named 'dns'")
                return original_import(name, globals, locals, fromlist, level)

            with patch.object(builtins, "__import__", mock_import):
                # Reload the module - this should trigger the ImportError path
                import custom_domain.services.dns as dns_module_reloaded

                # The module should have DNS_AVAILABLE = False
                assert dns_module_reloaded.DNS_AVAILABLE is False

        finally:
            # Restore original modules
            if dns_module is not None:
                sys.modules["dns"] = dns_module
            if dns_resolver_module is not None:
                sys.modules["dns.resolver"] = dns_resolver_module
            if app_dns_module is not None:
                sys.modules["custom_domain.services.dns"] = app_dns_module
            else:
                # Force reimport with dnspython available
                if "custom_domain.services.dns" in sys.modules:
                    del sys.modules["custom_domain.services.dns"]


class TestDNSCheckResult:
    """Tests for DNSCheckResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = DNSCheckResult(
            success=True,
            actual_value="apps.example.com",
            expected_value="apps.example.com",
        )
        assert result.success is True
        assert result.error_message is None

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = DNSCheckResult(
            success=False,
            actual_value="other.example.com",
            expected_value="apps.example.com",
            error_message="CNAME mismatch",
        )
        assert result.success is False
        assert result.error_message == "CNAME mismatch"


class TestDNSService:
    """Tests for DNSService."""

    def test_init_with_dns_available(self):
        """Test initialization when dnspython is available."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_resolver = MagicMock()
            mock_dns.resolver.Resolver.return_value = mock_resolver
            service = DNSService()
            assert service._resolver is not None

    def test_init_without_dns(self):
        """Test initialization when dnspython is not available."""
        with patch("custom_domain.services.dns.DNS_AVAILABLE", False):
            service = DNSService()
            assert service._resolver is None

    @pytest.mark.asyncio
    async def test_check_cname_success(self):
        """Test successful CNAME check."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            # Setup mock resolver
            mock_rdata = MagicMock()
            mock_rdata.target = "apps.example.com."
            mock_answers = [mock_rdata]

            mock_resolver = MagicMock()
            mock_resolver.resolve.return_value = mock_answers
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_cname("test.example.com", "apps.example.com")

            assert result.success is True
            assert result.actual_value == "apps.example.com"

    @pytest.mark.asyncio
    async def test_check_cname_mismatch(self):
        """Test CNAME check with mismatch."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_rdata = MagicMock()
            mock_rdata.target = "other.example.com."
            mock_answers = MagicMock()
            mock_answers.__iter__ = lambda self: iter([mock_rdata])
            mock_answers.__getitem__ = lambda self, i: mock_rdata

            mock_resolver = MagicMock()
            mock_resolver.resolve.return_value = mock_answers
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_cname("test.example.com", "apps.example.com")

            assert result.success is False
            assert (
                "mismatch" in result.error_message.lower()
                or "other.example.com" in result.actual_value
            )

    @pytest.mark.asyncio
    async def test_check_cname_nxdomain(self):
        """Test CNAME check when domain doesn't exist."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_dns.resolver.NXDOMAIN = Exception
            mock_resolver = MagicMock()
            mock_resolver.resolve.side_effect = mock_dns.resolver.NXDOMAIN()
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_cname("nonexistent.example.com", "apps.example.com")

            assert result.success is False
            assert "NXDOMAIN" in result.error_message or "not exist" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_check_cname_no_answer(self):
        """Test CNAME check when no CNAME record exists."""
        import dns.resolver as real_dns_resolver

        # Create service with real dns available
        service = DNSService()

        # Mock the resolver's resolve method to raise NoAnswer
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = real_dns_resolver.NoAnswer()
        service._resolver = mock_resolver

        result = await service.check_cname("test.example.com", "apps.example.com")

        assert result.success is False
        assert "No CNAME record" in result.error_message

    @pytest.mark.asyncio
    async def test_check_cname_timeout(self):
        """Test CNAME check on timeout."""
        import dns.resolver as real_dns_resolver

        # Create service with real dns available
        service = DNSService()

        # Mock the resolver's resolve method to raise Timeout
        mock_resolver = MagicMock()
        # LifetimeTimeout needs timeout and errors args
        mock_resolver.resolve.side_effect = real_dns_resolver.LifetimeTimeout(timeout=10, errors=[])
        service._resolver = mock_resolver

        result = await service.check_cname("test.example.com", "apps.example.com")

        assert result.success is False
        assert "timed out" in result.error_message

    @pytest.mark.asyncio
    async def test_check_cname_socket_fallback(self):
        """Test CNAME check using socket fallback."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", False),
            patch("socket.gethostbyname") as mock_gethostbyname,
        ):
            mock_gethostbyname.return_value = "1.2.3.4"

            service = DNSService()
            result = await service.check_cname("test.example.com", "apps.example.com")

            # Socket can't verify CNAME, so it should fail
            assert result.success is False
            assert "cannot verify" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_check_cname_socket_error(self):
        """Test CNAME check when socket fails."""
        import socket

        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", False),
            patch("socket.gethostbyname") as mock_gethostbyname,
        ):
            mock_gethostbyname.side_effect = socket.gaierror("DNS lookup failed")

            service = DNSService()
            result = await service.check_cname("test.example.com", "apps.example.com")

            assert result.success is False
            assert "failed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_check_cname_general_exception(self):
        """Test CNAME check with general exception."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve.side_effect = Exception("Unexpected error")
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_cname("test.example.com", "apps.example.com")

            assert result.success is False

    @pytest.mark.asyncio
    async def test_check_a_record_success(self):
        """Test successful A record check."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_rdata = MagicMock()
            mock_rdata.address = "1.2.3.4"
            mock_answers = [mock_rdata]

            mock_resolver = MagicMock()
            mock_resolver.resolve.return_value = mock_answers
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_a_record("test.example.com", "1.2.3.4")

            assert result.success is True
            assert result.actual_value == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_check_a_record_mismatch(self):
        """Test A record check with mismatch."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_rdata = MagicMock()
            mock_rdata.address = "5.6.7.8"
            mock_answers = MagicMock()
            mock_answers.__iter__ = lambda self: iter([mock_rdata])
            mock_answers.__getitem__ = lambda self, i: mock_rdata

            mock_resolver = MagicMock()
            mock_resolver.resolve.return_value = mock_answers
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_a_record("test.example.com", "1.2.3.4")

            assert result.success is False

    @pytest.mark.asyncio
    async def test_check_a_record_socket_fallback(self):
        """Test A record check using socket fallback."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", False),
            patch("socket.gethostbyname") as mock_gethostbyname,
        ):
            mock_gethostbyname.return_value = "1.2.3.4"

            service = DNSService()
            result = await service.check_a_record("test.example.com", "1.2.3.4")

            assert result.success is True
            assert result.actual_value == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_check_a_record_exception(self):
        """Test A record check with exception."""
        with (
            patch("custom_domain.services.dns.DNS_AVAILABLE", True),
            patch("custom_domain.services.dns.dns") as mock_dns,
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve.side_effect = Exception("DNS error")
            mock_dns.resolver.Resolver.return_value = mock_resolver

            service = DNSService()
            result = await service.check_a_record("test.example.com", "1.2.3.4")

            assert result.success is False


class TestResolverTimeout:
    """The resolver timeout is a setting."""

    def test_timeout_and_lifetime_follow_the_setting(self, monkeypatch):
        from custom_domain.config import settings
        from custom_domain.services import dns as dns_module

        monkeypatch.setattr(settings, "dns_timeout_seconds", 4)
        monkeypatch.setattr(dns_module, "DNS_AVAILABLE", True)
        monkeypatch.setattr(dns_module, "dns", MagicMock(), raising=False)

        service = dns_module.DNSService()

        assert service._resolver.timeout == 4
        assert service._resolver.lifetime == 4
