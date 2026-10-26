# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/certbot.py."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from custom_domain.services.certbot import (
    CertbotResult,
    CertbotService,
    CertificateInfo,
)


class TestCertbotResult:
    """Tests for CertbotResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        expires_at = datetime.now(UTC) + timedelta(days=90)
        result = CertbotResult(
            success=True,
            expires_at=expires_at,
        )
        assert result.success is True
        assert result.expires_at is not None

    def test_create_failure_result(self):
        """Test creating a failure result."""
        result = CertbotResult(
            success=False,
            error_message="Certificate provisioning failed",
        )
        assert result.success is False
        assert result.error_message is not None


class TestCertificateInfo:
    """Tests for CertificateInfo dataclass."""

    def test_create_certificate_info(self):
        """Test creating certificate info."""
        info = CertificateInfo(
            domain="test.example.com",
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=90),
            days_until_expiry=90,
        )
        assert info.domain == "test.example.com"
        assert info.days_until_expiry == 90


class TestCertbotService:
    """Tests for CertbotService."""

    def test_enabled_follows_the_setting(self, monkeypatch):
        """The service reads CERTBOT_ENABLED each time it is asked."""
        from custom_domain.config import settings

        service = CertbotService()
        monkeypatch.setattr(settings, "certbot_enabled", True)
        assert service.enabled is True
        monkeypatch.setattr(settings, "certbot_enabled", False)
        assert service.enabled is False

    @pytest.mark.asyncio
    async def test_provision_certificate_disabled(self):
        """Test provisioning when certbot is disabled returns success=True."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = False
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"
            service = CertbotService()
            result = await service.provision_certificate("test.example.com")
            # When disabled, it returns success=True with a message
            assert result.success is True
            assert result.error_message == "Certbot disabled"

    @pytest.mark.asyncio
    async def test_provision_certificate_success(self):
        """Test successful certificate provisioning (mocks certbot command)."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            # Mock asyncio.create_subprocess_exec for "sudo certbot certonly ..."
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                process.communicate = AsyncMock(return_value=(b"Certificate obtained", b""))
                mock_exec.return_value = process

                # Mock check_certificate to return cert info
                with patch.object(service, "check_certificate") as mock_check:
                    mock_check.return_value = CertificateInfo(
                        domain="test.example.com",
                        issued_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(days=90),
                        days_until_expiry=90,
                    )

                    result = await service.provision_certificate("test.example.com")

                    # Verify certbot was called with correct args
                    mock_exec.assert_called_once()
                    call_args = mock_exec.call_args[0]
                    assert "certbot-issue" in call_args
                    assert call_args[-1] == "test.example.com"
                    assert "--webroot" in call_args

                    assert result.success is True
                    assert result.expires_at is not None

    @pytest.mark.asyncio
    async def test_provision_certificate_challenge_failure(self):
        """Test certificate provisioning with challenge failure."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                process.communicate = AsyncMock(return_value=(b"", b"challenge failed"))
                mock_exec.return_value = process

                result = await service.provision_certificate("test.example.com")
                assert result.success is False
                assert "ACME challenge failed" in result.error_message

    @pytest.mark.asyncio
    async def test_provision_certificate_rate_limit(self):
        """Test certificate provisioning with rate limit error."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                process.communicate = AsyncMock(return_value=(b"", b"rate limit exceeded"))
                mock_exec.return_value = process

                result = await service.provision_certificate("test.example.com")
                assert result.success is False
                assert "rate limit" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_provision_certificate_exception(self):
        """Test certificate provisioning handles exceptions."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = Exception("Subprocess error")

                result = await service.provision_certificate("test.example.com")
                assert result.success is False
                assert "Subprocess error" in result.error_message

    @pytest.mark.asyncio
    async def test_check_certificate_exists(self):
        """Test checking an existing certificate (mocks openssl command)."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            # Mock Path.exists to simulate certificate exists
            # Mock openssl x509 command
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                process.communicate = AsyncMock(
                    return_value=(
                        b"notBefore=Jan  1 00:00:00 2024 GMT\nnotAfter=Apr  1 00:00:00 2024 GMT",
                        b"",
                    )
                )
                mock_exec.return_value = process

                info = await service.check_certificate("test.example.com")

                # Verify openssl was called
                mock_exec.assert_called_once()
                call_args = mock_exec.call_args[0]
                assert "cert-dates" in call_args
                assert call_args[-1] == "test.example.com"

                assert info is not None
                assert info.domain == "test.example.com"

    @pytest.mark.asyncio
    async def test_check_certificate_not_exists(self):
        """Test checking a non-existent certificate."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 3  # the helper's "no such certificate" status
                process.communicate = AsyncMock(return_value=(b"", b""))
                mock_exec.return_value = process

                info = await service.check_certificate("test.example.com")
                assert info is None

    @pytest.mark.asyncio
    async def test_check_certificate_openssl_error(self):
        """Test checking certificate with openssl error."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                process.communicate = AsyncMock(return_value=(b"", b"Error"))
                mock_exec.return_value = process

                info = await service.check_certificate("test.example.com")
                assert info is None

    @pytest.mark.asyncio
    async def test_renew_certificate_disabled(self):
        """Test renewal when certbot is disabled."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = False
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()
            result = await service.renew_certificate("test.example.com")
            assert result.success is True
            assert result.error_message == "Certbot disabled"

    @pytest.mark.asyncio
    async def test_renew_certificate_success(self):
        """Test successful certificate renewal (mocks certbot renew command)."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                process.communicate = AsyncMock(return_value=(b"Certificate renewed", b""))
                mock_exec.return_value = process

                with patch.object(service, "check_certificate") as mock_check:
                    mock_check.return_value = CertificateInfo(
                        domain="test.example.com",
                        issued_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(days=90),
                        days_until_expiry=90,
                    )

                    result = await service.renew_certificate("test.example.com")

                    # Verify certbot renew was called
                    mock_exec.assert_called_once()
                    call_args = mock_exec.call_args[0]
                    assert "certbot-renew" in call_args
                    assert call_args[-1] == "test.example.com"

                    assert result.success is True

    @pytest.mark.asyncio
    async def test_renew_certificate_failure(self):
        """Test certificate renewal failure."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                process.communicate = AsyncMock(return_value=(b"", b"Renewal failed"))
                mock_exec.return_value = process

                result = await service.renew_certificate("test.example.com")
                assert result.success is False

    @pytest.mark.asyncio
    async def test_revoke_certificate_disabled(self):
        """Test revocation when certbot is disabled."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = False
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()
            result = await service.revoke_certificate("test.example.com")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_revoke_certificate_not_exists(self):
        """Test revoking a non-existent certificate."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                process.communicate = AsyncMock(return_value=(b"certificate absent\n", b""))
                mock_exec.return_value = process

                result = await service.revoke_certificate("test.example.com")
                assert result.success is True
                assert result.error_message == "Certificate does not exist"

    @pytest.mark.asyncio
    async def test_revoke_certificate_success(self):
        """Test successful certificate revocation (mocks certbot revoke command)."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                process.communicate = AsyncMock(return_value=(b"Certificate revoked", b""))
                mock_exec.return_value = process

                result = await service.revoke_certificate("test.example.com")

                # Verify certbot revoke was called
                mock_exec.assert_called_once()
                call_args = mock_exec.call_args[0]
                assert "certbot-revoke" in call_args
                assert call_args[-1] == "test.example.com"

                assert result.success is True

    @pytest.mark.asyncio
    async def test_revoke_certificate_failure(self):
        """Test certificate revocation failure."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                process.communicate = AsyncMock(return_value=(b"", b"Revocation failed"))
                mock_exec.return_value = process

                result = await service.revoke_certificate("test.example.com")
                assert result.success is False

    @pytest.mark.asyncio
    async def test_provision_certificate_generic_error(self):
        """Test certificate provisioning with generic error (not rate limit or challenge)."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 1
                # Generic error not matching rate limit or challenge failure
                process.communicate = AsyncMock(return_value=(b"", b"Unknown configuration error"))
                mock_exec.return_value = process

                result = await service.provision_certificate("test.example.com")
                assert result.success is False
                assert "Unknown configuration error" in result.error_message

    @pytest.mark.asyncio
    async def test_check_certificate_no_notafter_match(self):
        """Test checking certificate when notAfter is not found in output."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                # Output without notAfter
                process.communicate = AsyncMock(
                    return_value=(b"notBefore=Jan  1 00:00:00 2024 GMT\n", b"")
                )
                mock_exec.return_value = process

                info = await service.check_certificate("test.example.com")
                assert info is None

    @pytest.mark.asyncio
    async def test_check_certificate_without_notbefore(self):
        """Test checking certificate without notBefore in output."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                process = AsyncMock()
                process.returncode = 0
                # Output with only notAfter, no notBefore
                process.communicate = AsyncMock(
                    return_value=(b"notAfter=Apr  1 00:00:00 2024 GMT\n", b"")
                )
                mock_exec.return_value = process

                info = await service.check_certificate("test.example.com")
                assert info is not None
                assert info.domain == "test.example.com"
                assert info.issued_at is None  # No notBefore

    @pytest.mark.asyncio
    async def test_check_certificate_exception(self):
        """Test checking certificate handles exceptions."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = Exception("Openssl error")

                info = await service.check_certificate("test.example.com")
                assert info is None

    @pytest.mark.asyncio
    async def test_renew_certificate_exception(self):
        """Test certificate renewal handles exceptions."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = Exception("Renewal subprocess error")

                result = await service.renew_certificate("test.example.com")
                assert result.success is False
                assert "Renewal subprocess error" in result.error_message

    @pytest.mark.asyncio
    async def test_revoke_certificate_exception(self):
        """Test certificate revocation handles exceptions."""
        with patch("custom_domain.services.certbot.settings") as mock_settings:
            mock_settings.certbot_enabled = True
            mock_settings.certbot_email = "admin@example.com"
            mock_settings.certbot_webroot = "/var/www/certbot"

            service = CertbotService()

            with patch("asyncio.create_subprocess_exec") as mock_exec:
                mock_exec.side_effect = Exception("Revocation subprocess error")

                result = await service.revoke_certificate("test.example.com")
                assert result.success is False
                assert "Revocation subprocess error" in result.error_message


class TestCertbotThroughHelper:
    """Everything privileged goes through the helper with the configured values."""

    @pytest.mark.asyncio
    async def test_issue_uses_configured_webroot_and_email(self):
        from custom_domain.services.privileged import build_command

        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        with (
            patch("asyncio.create_subprocess_exec", return_value=process) as mock_exec,
            patch.object(CertbotService, "check_certificate", return_value=None),
        ):
            await CertbotService().provision_certificate("test.example.com")
        assert mock_exec.call_args[0] == tuple(build_command("certbot-issue", "test.example.com"))
        assert "ops@example.invalid" in mock_exec.call_args[0]
        assert "/srv/acme" in mock_exec.call_args[0]

    @pytest.mark.asyncio
    async def test_missing_email_is_reported_without_running_anything(self, monkeypatch):
        from custom_domain.config import settings

        monkeypatch.setattr(settings, "certbot_email", "")
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            result = await CertbotService().provision_certificate("test.example.com")
        assert result.success is False
        assert "CERTBOT_EMAIL" in result.error_message
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_expiry_is_read_from_the_helper_output(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate = AsyncMock(
            return_value=(
                b"notBefore=Jan  1 00:00:00 2024 GMT\nnotAfter=Apr  1 00:00:00 2024 GMT\n",
                b"",
            )
        )
        with patch("asyncio.create_subprocess_exec", return_value=process):
            info = await CertbotService().check_certificate("test.example.com")
        assert info.expires_at == datetime(2024, 4, 1)
        assert info.issued_at == datetime(2024, 1, 1)
