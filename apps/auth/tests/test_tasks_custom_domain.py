# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.tasks.custom_domain — Custom domain provisioning tasks."""

import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from auth.db.models.tenant import CustomDomainStatus
from auth.tasks.custom_domain import (
    _check_dns_cname,
    _reload_nginx,
    _run_certbot,
    _update_tenant_status,
    _validate_domain,
    _write_nginx_config,
    check_pending_custom_domains,
    provision_custom_domain_ssl,
    remove_custom_domain_config,
    verify_custom_domain_dns,
)
from celery.exceptions import Retry

# ---------------------------------------------------------------------------
# _validate_domain
# ---------------------------------------------------------------------------


class TestValidateDomain:
    """Tests for _validate_domain."""

    def test_valid_simple_domain(self):
        assert _validate_domain("example.com") is True

    def test_valid_subdomain(self):
        assert _validate_domain("sub.example.com") is True

    def test_valid_hyphenated_cctld(self):
        assert _validate_domain("my-domain.co.uk") is True

    def test_invalid_leading_hyphen(self):
        assert _validate_domain("-example.com") is False

    def test_invalid_no_tld(self):
        assert _validate_domain("example") is False

    def test_invalid_dot_tld_only(self):
        assert _validate_domain(".com") is False

    def test_invalid_empty_string(self):
        assert _validate_domain("") is False


# ---------------------------------------------------------------------------
# _check_dns_cname
# ---------------------------------------------------------------------------


class TestCheckDnsCname:
    """Tests for _check_dns_cname.

    dns.resolver is imported locally inside _check_dns_cname, so we patch
    sys.modules to control what the ``import dns.resolver`` statement returns.
    """

    def _make_dns_mocks(self):
        """Create mock dns and dns.resolver modules."""
        mock_dns_resolver = MagicMock()
        mock_dns = MagicMock()
        mock_dns.resolver = mock_dns_resolver

        # Define exception classes that the source code catches
        mock_dns_resolver.NoAnswer = type("NoAnswer", (Exception,), {})
        mock_dns_resolver.NXDOMAIN = type("NXDOMAIN", (Exception,), {})

        return mock_dns, mock_dns_resolver

    def test_cname_matches_target(self):
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        mock_rdata = MagicMock()
        mock_rdata.target = "auth.example.com."
        mock_dns_resolver.resolve.return_value = [mock_rdata]

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is True
        assert "correctly points to" in msg

    def test_cname_points_elsewhere(self):
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        mock_rdata = MagicMock()
        mock_rdata.target = "other.server.com."
        mock_dns_resolver.resolve.return_value = [mock_rdata]

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is False
        assert "other.server.com" in msg

    def test_no_cname_but_a_record_exists(self):
        """No CNAME record, but an A record exists."""
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        a_rdata = MagicMock()

        # First call (CNAME) raises NoAnswer, second call (A) succeeds
        mock_dns_resolver.resolve.side_effect = [
            mock_dns_resolver.NoAnswer(),
            [a_rdata],
        ]

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is False
        assert "A record" in msg

    def test_nxdomain(self):
        """Domain does not exist (NXDOMAIN)."""
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        mock_dns_resolver.resolve.side_effect = mock_dns_resolver.NXDOMAIN()

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("nonexistent.example.com", "auth.example.com")

        assert valid is False
        assert "does not exist" in msg

    def test_no_dnspython_socket_resolves(self):
        """dnspython not installed; socket fallback resolves the domain."""
        # Setting dns and dns.resolver to None in sys.modules makes
        # ``import dns.resolver`` raise ImportError.
        with (
            patch.dict(sys.modules, {"dns": None, "dns.resolver": None}),
            patch("auth.tasks.custom_domain.socket.gethostbyname", return_value="1.2.3.4"),
        ):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is True
        assert "resolves" in msg

    def test_no_dnspython_socket_fails(self):
        """dnspython not installed; socket fallback also fails."""
        import socket as _socket

        with (
            patch.dict(sys.modules, {"dns": None, "dns.resolver": None}),
            patch(
                "auth.tasks.custom_domain.socket.gethostbyname",
                side_effect=_socket.gaierror("Name resolution failed"),
            ),
        ):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is False
        assert "does not resolve" in msg


# ---------------------------------------------------------------------------
# _write_nginx_config
# ---------------------------------------------------------------------------


class TestWriteNginxConfig:
    """Tests for _write_nginx_config.

    ``tempfile`` is imported locally inside the function, so we patch
    ``tempfile.NamedTemporaryFile`` at the module level.
    """

    def _mock_settings(self):
        s = MagicMock()
        s.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"
        s.custom_domain_nginx_ipv4 = "203.0.113.10"
        s.custom_domain_nginx_ipv6 = "2001:db8::10"
        s.custom_domain_upstream_socket = "/run/auth/auth.sock"
        return s

    @patch("auth.tasks.custom_domain.os.unlink")
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("tempfile.NamedTemporaryFile")
    @patch("auth.tasks.custom_domain.settings")
    def test_success(self, mock_settings_obj, mock_tmpfile, mock_run, mock_unlink):
        s = self._mock_settings()
        for attr in dir(s):
            if not attr.startswith("_"):
                setattr(mock_settings_obj, attr, getattr(s, attr))

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = True

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Configure the NamedTemporaryFile mock
        mock_tmp_instance = MagicMock()
        mock_tmp_instance.name = "/tmp/fake.conf"
        mock_tmp_instance.__enter__ = MagicMock(return_value=mock_tmp_instance)
        mock_tmp_instance.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = mock_tmp_instance

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            success, msg = _write_nginx_config("custom.example.com", "acme", ssl_ready=False)

        assert success is True
        assert "written" in msg.lower() or "Nginx" in msg

    @patch("auth.tasks.custom_domain.settings")
    def test_sites_dir_does_not_exist(self, mock_settings_obj):
        s = self._mock_settings()
        for attr in dir(s):
            if not attr.startswith("_"):
                setattr(mock_settings_obj, attr, getattr(s, attr))

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = False

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            success, msg = _write_nginx_config("custom.example.com", "acme")

        assert success is False
        assert "does not exist" in msg

    @patch("auth.tasks.custom_domain.settings")
    def test_no_ipv4_ipv6(self, mock_settings_obj):
        s = self._mock_settings()
        s.custom_domain_nginx_ipv4 = ""
        s.custom_domain_nginx_ipv6 = ""
        for attr in dir(s):
            if not attr.startswith("_"):
                setattr(mock_settings_obj, attr, getattr(s, attr))

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = True

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            success, msg = _write_nginx_config("custom.example.com", "acme")

        assert success is False
        assert "not configured" in msg

    @patch("auth.tasks.custom_domain.settings")
    def test_no_upstream_socket(self, mock_settings_obj):
        s = self._mock_settings()
        s.custom_domain_upstream_socket = ""
        for attr in dir(s):
            if not attr.startswith("_"):
                setattr(mock_settings_obj, attr, getattr(s, attr))

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = True

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            success, msg = _write_nginx_config("custom.example.com", "acme")

        assert success is False
        assert "Upstream socket not configured" in msg

    @patch("auth.tasks.custom_domain.os.unlink")
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("tempfile.NamedTemporaryFile")
    @patch("auth.tasks.custom_domain.settings")
    def test_subprocess_fails(self, mock_settings_obj, mock_tmpfile, mock_run, mock_unlink):
        s = self._mock_settings()
        for attr in dir(s):
            if not attr.startswith("_"):
                setattr(mock_settings_obj, attr, getattr(s, attr))

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = True

        mock_run.return_value = MagicMock(returncode=1, stderr="permission denied")

        mock_tmp_instance = MagicMock()
        mock_tmp_instance.name = "/tmp/fake.conf"
        mock_tmp_instance.__enter__ = MagicMock(return_value=mock_tmp_instance)
        mock_tmp_instance.__exit__ = MagicMock(return_value=False)
        mock_tmpfile.return_value = mock_tmp_instance

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            success, msg = _write_nginx_config("custom.example.com", "acme")

        assert success is False
        assert "Failed to write nginx config" in msg


# ---------------------------------------------------------------------------
# _reload_nginx
# ---------------------------------------------------------------------------


class TestReloadNginx:
    """Tests for _reload_nginx."""

    @patch("auth.tasks.custom_domain.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        success, msg = _reload_nginx()
        assert success is True
        assert "successfully" in msg.lower()
        assert mock_run.call_count == 2  # nginx -t + systemctl reload

    @patch("auth.tasks.custom_domain.subprocess.run")
    def test_config_test_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="syntax error")
        success, msg = _reload_nginx()
        assert success is False
        assert "config test failed" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    def test_reload_fails(self, mock_run):
        # First call (nginx -t) succeeds, second call (reload) fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr=""),
            MagicMock(returncode=1, stderr="reload error"),
        ]
        success, msg = _reload_nginx()
        assert success is False
        assert "reload failed" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="nginx", timeout=30)
        success, msg = _reload_nginx()
        assert success is False
        assert "timed out" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    def test_command_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        success, msg = _reload_nginx()
        assert success is False
        assert "not found" in msg.lower()


# ---------------------------------------------------------------------------
# _run_certbot
# ---------------------------------------------------------------------------


class TestRunCertbot:
    """Tests for _run_certbot."""

    def test_no_email(self):
        success, msg = _run_certbot("custom.example.com", "")
        assert success is False
        assert "email not configured" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_success(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is True
        assert "obtained" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_rate_limit_error(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.return_value = MagicMock(
            returncode=1, stderr="Rate limit exceeded for registrations"
        )
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "rate limit" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_unauthorized_error(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.return_value = MagicMock(
            returncode=1, stderr="Unauthorized: invalid response from server"
        )
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "verification failed" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_connection_refused(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.return_value = MagicMock(returncode=1, stderr="Connection refused to host")
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "could not connect" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_general_failure(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.return_value = MagicMock(returncode=1, stderr="some unknown error")
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "certbot failed" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_timeout(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="certbot", timeout=120)
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "timed out" in msg.lower()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_command_not_found(self, mock_path_cls, mock_run):
        mock_webroot = MagicMock()
        mock_webroot.exists.return_value = True
        mock_path_cls.return_value = mock_webroot

        mock_run.side_effect = FileNotFoundError("certbot not found")
        success, msg = _run_certbot("custom.example.com", "admin@example.com")
        assert success is False
        assert "not found" in msg.lower()


# ---------------------------------------------------------------------------
# _update_tenant_status
# ---------------------------------------------------------------------------


class TestUpdateTenantStatus:
    """Tests for _update_tenant_status.

    sqlalchemy.create_engine and sqlalchemy.orm.Session are imported locally
    inside the function body, so we patch them at their original module paths.
    """

    @patch("auth.tasks.custom_domain.settings")
    def test_basic_update(self, mock_settings):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"

        mock_session_instance = MagicMock()
        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine) as mock_ce,
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
            mock_session_instance.__exit__ = MagicMock(return_value=False)

            tenant_id = str(uuid.uuid4())
            _update_tenant_status(tenant_id, CustomDomainStatus.PENDING, error="test error")

            mock_ce.assert_called_once()
            mock_session_instance.execute.assert_called_once()
            mock_session_instance.commit.assert_called_once()

    @patch("auth.tasks.custom_domain.settings")
    def test_with_dns_verified(self, mock_settings):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"

        mock_session_instance = MagicMock()
        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
            mock_session_instance.__exit__ = MagicMock(return_value=False)

            tenant_id = str(uuid.uuid4())
            _update_tenant_status(
                tenant_id,
                CustomDomainStatus.DNS_VERIFIED,
                dns_verified=True,
            )

            mock_session_instance.execute.assert_called_once()
            mock_session_instance.commit.assert_called_once()

    @patch("auth.tasks.custom_domain.settings")
    def test_with_ssl_provisioned(self, mock_settings):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"

        mock_session_instance = MagicMock()
        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
            mock_session_instance.__exit__ = MagicMock(return_value=False)

            tenant_id = str(uuid.uuid4())
            _update_tenant_status(
                tenant_id,
                CustomDomainStatus.ACTIVE,
                ssl_provisioned=True,
            )

            mock_session_instance.execute.assert_called_once()
            mock_session_instance.commit.assert_called_once()


# ---------------------------------------------------------------------------
# verify_custom_domain_dns (Celery task, bind=True)
# ---------------------------------------------------------------------------


class TestVerifyCustomDomainDns:
    """Tests for the verify_custom_domain_dns Celery task.

    This is a ``bind=True`` Celery task — Celery injects ``self`` automatically.
    Tests call the task directly without passing a mock_self argument.
    For retry/max-retry tests we use ``patch.object`` on the task object itself.
    """

    @patch("auth.tasks.custom_domain._update_tenant_status")
    def test_invalid_domain_fails(self, mock_update):
        tenant_id = str(uuid.uuid4())

        result = verify_custom_domain_dns(tenant_id, "-bad-domain", "acme")

        assert result["status"] == "failed"
        assert "Invalid domain" in result["error"]
        mock_update.assert_called_once_with(
            tenant_id,
            CustomDomainStatus.FAILED,
            error=result["error"],
        )

    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_no_cname_target_configured(self, mock_settings, mock_update):
        mock_settings.custom_domain_cname_target = ""
        tenant_id = str(uuid.uuid4())

        result = verify_custom_domain_dns(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "failed"
        assert "CNAME target not configured" in result["error"]

    @patch("auth.tasks.custom_domain._check_dns_cname", return_value=(False, "CNAME not found"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_dns_check_fails_retries(self, mock_settings, mock_update, mock_dns):
        mock_settings.custom_domain_cname_target = "auth.example.com"
        tenant_id = str(uuid.uuid4())

        with patch.object(
            verify_custom_domain_dns, "retry", side_effect=Retry("retry")
        ) as mock_retry:
            with pytest.raises(Retry):
                verify_custom_domain_dns(tenant_id, "custom.example.com", "acme")
            mock_retry.assert_called_once()

    @patch("auth.tasks.custom_domain._check_dns_cname", return_value=(False, "CNAME not found"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_dns_check_fails_max_retries(self, mock_settings, mock_update, mock_dns):
        mock_settings.custom_domain_cname_target = "auth.example.com"
        tenant_id = str(uuid.uuid4())

        with patch.object(
            verify_custom_domain_dns,
            "retry",
            side_effect=verify_custom_domain_dns.MaxRetriesExceededError(),
        ):
            result = verify_custom_domain_dns(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "pending"
        # Should have been called with PENDING status and an error about manual verification
        calls = mock_update.call_args_list
        last_call = calls[-1]
        assert last_call[0][1] == CustomDomainStatus.PENDING
        assert "manually" in last_call[1]["error"]

    @patch("auth.tasks.custom_domain.provision_custom_domain_ssl")
    @patch(
        "auth.tasks.custom_domain._check_dns_cname",
        return_value=(True, "CNAME correctly points to auth.example.com"),
    )
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_dns_valid_triggers_ssl(self, mock_settings, mock_update, mock_dns, mock_provision):
        mock_settings.custom_domain_cname_target = "auth.example.com"
        tenant_id = str(uuid.uuid4())

        result = verify_custom_domain_dns(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "dns_verified"
        mock_provision.delay.assert_called_once_with(tenant_id, "custom.example.com", "acme")
        # Verify status was updated to DNS_VERIFIED
        update_calls = mock_update.call_args_list
        dns_verified_call = [c for c in update_calls if c[0][1] == CustomDomainStatus.DNS_VERIFIED]
        assert len(dns_verified_call) == 1


# ---------------------------------------------------------------------------
# provision_custom_domain_ssl (Celery task, bind=True)
# ---------------------------------------------------------------------------


class TestProvisionCustomDomainSsl:
    """Tests for the provision_custom_domain_ssl Celery task.

    This is a ``bind=True`` Celery task — Celery injects ``self`` automatically.
    Tests call the task directly without passing a mock_self argument.
    """

    @patch(
        "auth.tasks.custom_domain._write_nginx_config", return_value=(False, "sites dir missing")
    )
    @patch("auth.tasks.custom_domain._update_tenant_status")
    def test_nginx_write_fails(self, mock_update, mock_write):
        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "failed"
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.FAILED, error="sites dir missing")

    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(False, "config test failed"))
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    def test_nginx_reload_fails(self, mock_update, mock_write, mock_reload):
        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "failed"
        mock_update.assert_any_call(
            tenant_id, CustomDomainStatus.FAILED, error="config test failed"
        )

    @patch("auth.tasks.custom_domain._run_certbot", return_value=(False, "certbot failed"))
    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_certbot_fails_retries(
        self, mock_settings, mock_update, mock_write, mock_reload, mock_certbot
    ):
        mock_settings.custom_domain_certbot_enabled = True
        mock_settings.custom_domain_certbot_email = "admin@example.com"

        tenant_id = str(uuid.uuid4())

        with patch.object(
            provision_custom_domain_ssl, "retry", side_effect=Retry("retry")
        ) as mock_retry:
            with pytest.raises(Retry):
                provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")
            mock_retry.assert_called_once()

    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_certbot_disabled_success(self, mock_settings, mock_update, mock_write, mock_reload):
        mock_settings.custom_domain_certbot_enabled = False

        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "active"
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.ACTIVE, ssl_provisioned=True)

    @patch("auth.tasks.custom_domain._run_certbot", return_value=(True, "obtained"))
    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_full_success(self, mock_settings, mock_update, mock_write, mock_reload, mock_certbot):
        mock_settings.custom_domain_certbot_enabled = True
        mock_settings.custom_domain_certbot_email = "admin@example.com"

        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result["status"] == "active"
        assert "active" in result["message"].lower() or "active" in result["status"]

        # nginx config written twice: HTTP-only then full SSL
        assert mock_write.call_count == 2
        # nginx reloaded twice
        assert mock_reload.call_count == 2
        # certbot called once
        mock_certbot.assert_called_once_with("custom.example.com", "admin@example.com")
        # final status is ACTIVE with ssl_provisioned
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.ACTIVE, ssl_provisioned=True)


# ---------------------------------------------------------------------------
# check_pending_custom_domains (Celery task, NOT bind=True)
# ---------------------------------------------------------------------------


class TestCheckPendingCustomDomains:
    """Tests for the check_pending_custom_domains Celery task."""

    @patch("auth.tasks.custom_domain.settings")
    def test_no_pending_tenants(self, mock_settings):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"
        mock_settings.custom_domain_dns_check_interval_minutes = 5

        mock_session_instance = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_session_instance.execute.return_value = mock_execute
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            result = check_pending_custom_domains()

        assert result["status"] == "completed"
        assert result["checked_count"] == 0

    @patch("auth.tasks.custom_domain.verify_custom_domain_dns")
    @patch("auth.tasks.custom_domain.settings")
    def test_triggers_dns_check_for_pending_tenant(self, mock_settings, mock_verify):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"
        mock_settings.custom_domain_dns_check_interval_minutes = 5

        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()
        mock_tenant.custom_domain = "custom.example.com"
        mock_tenant.slug = "acme"
        mock_tenant.custom_domain_checked_at = None  # never checked

        mock_session_instance = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_tenant]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_session_instance.execute.return_value = mock_execute
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            result = check_pending_custom_domains()

        assert result["checked_count"] == 1
        mock_verify.delay.assert_called_once_with(
            str(mock_tenant.id),
            "custom.example.com",
            "acme",
        )

    @patch("auth.tasks.custom_domain.verify_custom_domain_dns")
    @patch("auth.tasks.custom_domain.settings")
    def test_skips_recently_checked_tenant(self, mock_settings, mock_verify):
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"
        mock_settings.custom_domain_dns_check_interval_minutes = 5

        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()
        mock_tenant.custom_domain = "custom.example.com"
        mock_tenant.slug = "acme"
        # Checked 2 minutes ago (below the 5-minute threshold)
        mock_tenant.custom_domain_checked_at = datetime.now(UTC) - timedelta(minutes=2)

        mock_session_instance = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_tenant]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_session_instance.execute.return_value = mock_execute
        mock_session_instance.__enter__ = MagicMock(return_value=mock_session_instance)
        mock_session_instance.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session_instance),
        ):
            result = check_pending_custom_domains()

        assert result["checked_count"] == 0
        mock_verify.delay.assert_not_called()


# ---------------------------------------------------------------------------
# remove_custom_domain_config (Celery task, bind=True)
# ---------------------------------------------------------------------------


class TestRemoveCustomDomainConfig:
    """Tests for the remove_custom_domain_config Celery task.

    This is a ``bind=True`` Celery task — Celery injects ``self`` automatically.
    Tests call the task directly without passing a mock_self argument.
    """

    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.settings")
    def test_config_exists_removed_successfully(self, mock_settings, mock_run, mock_reload):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = True

        mock_sites_dir = MagicMock()
        mock_sites_dir.__truediv__ = MagicMock(return_value=mock_config_path)

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            result = remove_custom_domain_config("custom.example.com", "acme")

        assert result["status"] == "removed"
        mock_run.assert_called_once()
        mock_reload.assert_called_once()

    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.settings")
    def test_config_does_not_exist(self, mock_settings, mock_run):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        mock_config_path = MagicMock()
        mock_config_path.exists.return_value = False

        mock_sites_dir = MagicMock()
        mock_sites_dir.__truediv__ = MagicMock(return_value=mock_config_path)

        with patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir):
            result = remove_custom_domain_config("custom.example.com", "acme")

        assert result["status"] == "removed"
        mock_run.assert_not_called()

    @patch("auth.tasks.custom_domain.settings")
    def test_removal_fails_retries(self, mock_settings):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        mock_config_path = MagicMock()
        mock_config_path.exists.side_effect = OSError("disk error")

        mock_sites_dir = MagicMock()
        mock_sites_dir.__truediv__ = MagicMock(return_value=mock_config_path)

        with patch.object(
            remove_custom_domain_config, "retry", side_effect=Retry("retry")
        ) as mock_retry:
            with (
                patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir),
                pytest.raises(Retry),
            ):
                remove_custom_domain_config("custom.example.com", "acme")
            mock_retry.assert_called_once_with(countdown=60)

    @patch("auth.tasks.custom_domain.settings")
    def test_removal_fails_max_retries(self, mock_settings):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        mock_config_path = MagicMock()
        mock_config_path.exists.side_effect = OSError("disk error")

        mock_sites_dir = MagicMock()
        mock_sites_dir.__truediv__ = MagicMock(return_value=mock_config_path)

        with (
            patch.object(
                remove_custom_domain_config,
                "retry",
                side_effect=remove_custom_domain_config.MaxRetriesExceededError(),
            ),
            patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir),
        ):
            result = remove_custom_domain_config("custom.example.com", "acme")

        assert result["status"] == "failed"
        assert "disk error" in result["error"]


# ---------------------------------------------------------------------------
# Remaining branch coverage
# ---------------------------------------------------------------------------


class TestCheckDnsCnameExtra(TestCheckDnsCname):
    def test_expected_target_with_trailing_dot_matches(self):
        """A configured CNAME target written with a trailing dot still matches."""
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        mock_rdata = MagicMock()
        mock_rdata.target = "auth.example.com."
        mock_dns_resolver.resolve.return_value = [mock_rdata]

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com.")

        assert valid is True
        assert "correctly points to" in msg

    def test_no_cname_and_no_a_record(self):
        """Neither a CNAME nor an A record exists for the domain."""
        mock_dns, mock_dns_resolver = self._make_dns_mocks()

        mock_dns_resolver.resolve.side_effect = [
            mock_dns_resolver.NoAnswer(),
            mock_dns_resolver.NoAnswer(),
        ]

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            valid, msg = _check_dns_cname("custom.example.com", "auth.example.com")

        assert valid is False
        assert "No DNS records found" in msg


class TestWriteNginxConfigOsError:
    @patch("auth.tasks.custom_domain.settings")
    def test_oserror_is_reported(self, mock_settings_obj):
        mock_settings_obj.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"
        mock_settings_obj.custom_domain_nginx_ipv4 = "203.0.113.10"
        mock_settings_obj.custom_domain_nginx_ipv6 = "2001:db8::10"
        mock_settings_obj.custom_domain_upstream_socket = "/run/auth/auth.sock"

        mock_sites_dir = MagicMock()
        mock_sites_dir.exists.return_value = True

        with (
            patch("auth.tasks.custom_domain.Path", return_value=mock_sites_dir),
            patch("tempfile.NamedTemporaryFile", side_effect=OSError("no space left")),
        ):
            success, msg = _write_nginx_config("custom.example.com", "acme", ssl_ready=False)

        assert success is False
        assert "no space left" in msg


class TestReloadNginxUnexpectedError:
    @patch("auth.tasks.custom_domain.subprocess.run", side_effect=RuntimeError("boom"))
    def test_generic_exception_is_reported(self, mock_run):
        success, msg = _reload_nginx()

        assert success is False
        assert msg == "Nginx reload error: boom"


class TestRunCertbotExtra:
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.Path")
    def test_creates_missing_webroot(self, mock_path_cls, mock_run):
        webroot = MagicMock()
        webroot.exists.return_value = False
        mock_path_cls.return_value = webroot
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        success, _msg = _run_certbot("custom.example.com", "admin@example.com")

        assert success is True
        # First call creates the webroot, second runs certbot.
        assert mock_run.call_count == 2
        assert mock_run.call_args_list[0][0][0][:2] == ["/usr/bin/sudo", "mkdir"]

    @patch("auth.tasks.custom_domain.subprocess.run", side_effect=RuntimeError("boom"))
    @patch("auth.tasks.custom_domain.Path")
    def test_generic_exception_is_reported(self, mock_path_cls, mock_run):
        webroot = MagicMock()
        webroot.exists.return_value = True
        mock_path_cls.return_value = webroot

        success, msg = _run_certbot("custom.example.com", "admin@example.com")

        assert success is False
        assert msg == "Certbot error: boom"


class TestProvisionCustomDomainSslFailureTails:
    """The failure paths that run *after* certbot has succeeded or exhausted retries."""

    @patch("auth.tasks.custom_domain._run_certbot", return_value=(False, "certbot failed"))
    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_certbot_max_retries_marks_failed(
        self, mock_settings, mock_update, mock_write, mock_reload, mock_certbot
    ):
        mock_settings.custom_domain_certbot_enabled = True
        mock_settings.custom_domain_certbot_email = "admin@example.com"
        tenant_id = str(uuid.uuid4())

        with patch.object(
            provision_custom_domain_ssl,
            "retry",
            side_effect=provision_custom_domain_ssl.MaxRetriesExceededError(),
        ):
            result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result == {"status": "failed", "error": "certbot failed"}
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.FAILED, error="certbot failed")

    @patch("auth.tasks.custom_domain._run_certbot", return_value=(True, "obtained"))
    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._write_nginx_config")
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_ssl_config_write_fails(
        self, mock_settings, mock_update, mock_write, mock_reload, mock_certbot
    ):
        mock_settings.custom_domain_certbot_enabled = True
        mock_settings.custom_domain_certbot_email = "admin@example.com"
        # HTTP-only config succeeds, the SSL rewrite fails.
        mock_write.side_effect = [(True, "ok"), (False, "ssl write failed")]
        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result == {"status": "failed", "error": "ssl write failed"}
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.FAILED, error="ssl write failed")

    @patch("auth.tasks.custom_domain._run_certbot", return_value=(True, "obtained"))
    @patch("auth.tasks.custom_domain._reload_nginx")
    @patch("auth.tasks.custom_domain._write_nginx_config", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain._update_tenant_status")
    @patch("auth.tasks.custom_domain.settings")
    def test_final_reload_fails(
        self, mock_settings, mock_update, mock_write, mock_reload, mock_certbot
    ):
        mock_settings.custom_domain_certbot_enabled = True
        mock_settings.custom_domain_certbot_email = "admin@example.com"
        mock_reload.side_effect = [(True, "ok"), (False, "reload failed")]
        tenant_id = str(uuid.uuid4())

        result = provision_custom_domain_ssl(tenant_id, "custom.example.com", "acme")

        assert result == {"status": "failed", "error": "reload failed"}
        mock_update.assert_any_call(tenant_id, CustomDomainStatus.FAILED, error="reload failed")


class TestCheckPendingCustomDomainsStaleCheck:
    @patch("auth.tasks.custom_domain.verify_custom_domain_dns")
    @patch("auth.tasks.custom_domain.settings")
    def test_stale_check_is_retriggered(self, mock_settings, mock_verify):
        """A tenant checked longer ago than the interval is re-queued."""
        mock_settings.database_url = "postgresql+asyncpg://localhost/auth"
        mock_settings.custom_domain_dns_check_interval_minutes = 5

        mock_tenant = MagicMock()
        mock_tenant.id = uuid.uuid4()
        mock_tenant.custom_domain = "custom.example.com"
        mock_tenant.slug = "acme"
        mock_tenant.custom_domain_checked_at = datetime.now(UTC) - timedelta(minutes=30)

        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [mock_tenant]
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        with (
            patch("sqlalchemy.create_engine", return_value=MagicMock()),
            patch("sqlalchemy.orm.Session", return_value=session),
        ):
            result = check_pending_custom_domains()

        assert result["checked_count"] == 1
        mock_verify.delay.assert_called_once()


class TestRemoveCustomDomainConfigFailures:
    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(True, "ok"))
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.settings")
    def test_rm_failure_is_logged_but_not_fatal(self, mock_settings, mock_run, mock_reload):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        config_path = MagicMock()
        config_path.exists.return_value = True
        sites_dir = MagicMock()
        sites_dir.__truediv__ = MagicMock(return_value=config_path)

        mock_run.return_value = MagicMock(returncode=1, stderr="permission denied")

        with patch("auth.tasks.custom_domain.Path", return_value=sites_dir):
            result = remove_custom_domain_config("custom.example.com", "acme")

        assert result == {"status": "removed", "domain": "custom.example.com"}

    @patch("auth.tasks.custom_domain._reload_nginx", return_value=(False, "reload failed"))
    @patch("auth.tasks.custom_domain.subprocess.run")
    @patch("auth.tasks.custom_domain.settings")
    def test_reload_failure_is_logged_but_not_fatal(self, mock_settings, mock_run, mock_reload):
        mock_settings.custom_domain_nginx_sites_dir = "/etc/nginx/sites-enabled"

        config_path = MagicMock()
        config_path.exists.return_value = True
        sites_dir = MagicMock()
        sites_dir.__truediv__ = MagicMock(return_value=config_path)

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with patch("auth.tasks.custom_domain.Path", return_value=sites_dir):
            result = remove_custom_domain_config("custom.example.com", "acme")

        assert result == {"status": "removed", "domain": "custom.example.com"}
