# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/tasks/maintenance.py."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from custom_domain.models.enums import DomainStatus


class TestSoftDeleteDomain:
    """Tests for soft_delete_domain function."""

    def test_soft_delete_domain(self):
        """Test soft deleting a domain."""
        from custom_domain.tasks.maintenance import soft_delete_domain

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.deleted_at = None

        mock_db = MagicMock()

        with patch("custom_domain.tasks.maintenance.deprovision_domain") as mock_deprovision:
            mock_deprovision.delay = MagicMock()

            soft_delete_domain(mock_db, mock_domain, "Test reason")

            assert mock_domain.deleted_at is not None
            assert mock_domain.error_message == "Test reason"
            mock_db.commit.assert_called_once()
            mock_deprovision.delay.assert_called_once_with(str(mock_domain.id), False)


class TestCheckCertificateExpiry:
    """Tests for check_certificate_expiry task."""

    def test_checks_expiring_certificates(self):
        """Test task checks expiring certificates."""
        from custom_domain.tasks.maintenance import check_certificate_expiry

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.ssl_expires_at = datetime.now(UTC) + timedelta(days=10)

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_domain]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.certbot_service") as mock_certbot:
                mock_cert_info = MagicMock()
                mock_cert_info.days_until_expiry = 10
                mock_certbot.check_certificate = MagicMock(return_value=mock_cert_info)

                with patch("custom_domain.tasks.maintenance.run_async") as mock_run:
                    mock_run.return_value = mock_cert_info

                    with patch(
                        "custom_domain.tasks.maintenance.provision_domain_ssl"
                    ) as mock_provision:
                        mock_provision.delay = MagicMock()

                        with patch("custom_domain.tasks.maintenance.settings") as mock_settings:
                            mock_settings.certificate_renewal_days = 30

                            check_certificate_expiry()

                            # Should trigger renewal
                            mock_provision.delay.assert_called_once()

    def test_skips_healthy_certificates(self):
        """Test task skips certificates not expiring soon."""
        from custom_domain.tasks.maintenance import check_certificate_expiry

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.settings") as mock_settings:
                mock_settings.certificate_renewal_days = 30

                check_certificate_expiry()


class TestCheckDomainHealth:
    """Tests for check_domain_health task."""

    def test_checks_active_domains(self):
        """Test task checks active domains."""
        from custom_domain.tasks.maintenance import check_domain_health

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.ACTIVE

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_domain]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.dns_service") as mock_dns:
                mock_result = MagicMock()
                mock_result.success = True
                mock_dns.check_cname = MagicMock(return_value=mock_result)

                with patch("custom_domain.tasks.maintenance.run_async") as mock_run:
                    mock_run.return_value = mock_result

                    check_domain_health()

                    assert mock_domain.error_message is None

    def test_marks_unhealthy_domains(self):
        """Test task marks unhealthy domains as failed."""
        from custom_domain.tasks.maintenance import check_domain_health

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.cname_target = "apps.example.com"
        mock_domain.status = DomainStatus.ACTIVE

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_domain]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.dns_service") as mock_dns:
                mock_result = MagicMock()
                mock_result.success = False
                mock_result.error_message = "CNAME not found"
                mock_dns.check_cname = MagicMock(return_value=mock_result)

                with patch("custom_domain.tasks.maintenance.run_async") as mock_run:
                    mock_run.return_value = mock_result

                    with patch(
                        "custom_domain.tasks.maintenance.soft_delete_domain"
                    ) as mock_soft_delete:
                        check_domain_health()

                        assert mock_domain.status == DomainStatus.FAILED
                        mock_soft_delete.assert_called_once()


class TestCleanupStaleDomains:
    """Tests for cleanup_stale_domains task."""

    def test_cleans_up_stale_domains(self):
        """Test task cleans up stale domains."""
        from custom_domain.tasks.maintenance import cleanup_stale_domains

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.PENDING
        mock_domain.created_at = datetime.now(UTC) - timedelta(hours=100)

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_domain]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with (
                patch("custom_domain.tasks.maintenance.soft_delete_domain") as mock_soft_delete,
                patch("custom_domain.tasks.maintenance.settings") as mock_settings,
            ):
                mock_settings.domain_activation_timeout_hours = 72

                cleanup_stale_domains()

                mock_soft_delete.assert_called_once()

    def test_skips_recent_domains(self):
        """Test task skips recently created domains."""
        from custom_domain.tasks.maintenance import cleanup_stale_domains

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.settings") as mock_settings:
                mock_settings.domain_activation_timeout_hours = 72

                cleanup_stale_domains()


class TestPurgeDeletedDomains:
    """Tests for purge_deleted_domains task."""

    def test_purges_old_deleted_domains(self):
        """Test task permanently deletes old soft-deleted domains."""
        from custom_domain.tasks.maintenance import purge_deleted_domains

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.deleted_at = datetime.now(UTC) - timedelta(days=100)

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = [mock_domain]
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.settings") as mock_settings:
                mock_settings.soft_delete_purge_days = 30

                purge_deleted_domains()

                mock_session.delete.assert_called_once_with(mock_domain)
                mock_session.commit.assert_called_once()

    def test_skips_recent_deleted_domains(self):
        """Test task skips recently deleted domains."""
        from custom_domain.tasks.maintenance import purge_deleted_domains

        with patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db:
            mock_session = MagicMock()
            mock_session.execute.return_value.scalars.return_value.all.return_value = []
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_get_db.return_value.__exit__ = MagicMock()

            with patch("custom_domain.tasks.maintenance.settings") as mock_settings:
                mock_settings.soft_delete_purge_days = 30

                purge_deleted_domains()

                mock_session.delete.assert_not_called()


class TestCheckCertificateExpiryNoCertInfo:
    """Test check_certificate_expiry when cert_info is None (line 67->57)."""

    def test_check_certificate_expiry_cert_info_none(self):
        """Test that domains are skipped when cert_info is None."""
        from custom_domain.tasks.maintenance import check_certificate_expiry

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.ssl_expires_at = datetime.now(UTC) + timedelta(days=5)

        with (
            patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db,
            patch("custom_domain.tasks.maintenance.certbot_service") as mock_certbot,
            patch("custom_domain.tasks.maintenance.run_async") as mock_run_async,
            patch("custom_domain.tasks.maintenance.provision_domain_ssl") as mock_provision,
            patch("custom_domain.tasks.maintenance.settings") as mock_settings,
        ):
            mock_db = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_domain]
            mock_db.execute.return_value = mock_result

            # Mock certbot to return a non-coroutine
            mock_certbot.check_certificate = MagicMock(return_value="fake_coro")
            # cert_info is None - this should skip renewal
            mock_run_async.return_value = None

            mock_settings.certificate_renewal_days = 30

            check_certificate_expiry()

            # provision_domain_ssl should NOT be called because cert_info is None
            mock_provision.delay.assert_not_called()

    def test_check_certificate_expiry_cert_healthy(self):
        """Test that domains are skipped when certificate is still healthy."""
        from custom_domain.tasks.maintenance import check_certificate_expiry

        mock_domain = MagicMock()
        mock_domain.id = uuid4()
        mock_domain.domain = "test.example.com"
        mock_domain.status = DomainStatus.ACTIVE
        mock_domain.ssl_expires_at = datetime.now(UTC) + timedelta(days=5)

        mock_cert_info = MagicMock()
        mock_cert_info.days_until_expiry = 60  # More than threshold

        with (
            patch("custom_domain.tasks.maintenance.get_sync_db") as mock_get_db,
            patch("custom_domain.tasks.maintenance.certbot_service") as mock_certbot,
            patch("custom_domain.tasks.maintenance.run_async") as mock_run_async,
            patch("custom_domain.tasks.maintenance.provision_domain_ssl") as mock_provision,
            patch("custom_domain.tasks.maintenance.settings") as mock_settings,
        ):
            mock_db = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_domain]
            mock_db.execute.return_value = mock_result

            # Mock certbot to return a non-coroutine
            mock_certbot.check_certificate = MagicMock(return_value="fake_coro")
            # cert_info shows healthy certificate (days > threshold)
            mock_run_async.return_value = mock_cert_info

            mock_settings.certificate_renewal_days = 30

            check_certificate_expiry()

            # provision_domain_ssl should NOT be called because cert is healthy
            mock_provision.delay.assert_not_called()
