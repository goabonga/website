# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/nginx.py."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_domain.config import ConfigurationError, settings
from custom_domain.services.nginx import nginx_manager
from custom_domain.services.privileged import PrivilegedResult


class TestNginxManager:
    """Tests for NginxManager."""

    def test_config_filename(self):
        """Test config filename generation."""
        filename = nginx_manager._config_filename("test.example.com")
        assert filename == "custom-domain-test.example.com.conf"

    def test_config_filename_uses_configured_prefix(self, monkeypatch):
        """The prefix of the generated files is a setting."""
        monkeypatch.setattr(settings, "nginx_config_prefix", "edge-")
        assert nginx_manager._config_filename("a.example.com") == "edge-a.example.com.conf"

    @pytest.mark.asyncio
    async def test_generate_http_config(self):
        """Test generating HTTP config with custom template."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.metadata_ = {}
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"

        mock_template = MagicMock()
        mock_template.http_template = "server { listen 80; server_name {{ domain }}; }"

        with patch("custom_domain.services.nginx.template_service") as mock_ts:
            mock_ts.render_template.return_value = (
                "server { listen 80; server_name test.example.com; }"
            )
            config = await nginx_manager.generate_http_config(mock_domain, mock_template)
            assert "test.example.com" in config

    @pytest.mark.asyncio
    async def test_generate_http_config_no_template(self):
        """Test generating HTTP config without template (uses default)."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.metadata_ = {}
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"

        with patch("custom_domain.services.nginx.template_service") as mock_ts:
            mock_ts.render_default_http.return_value = "server { listen 80; }"
            config = await nginx_manager.generate_http_config(mock_domain, None)
            assert "server" in config

    @pytest.mark.asyncio
    async def test_generate_https_config(self):
        """Test generating HTTPS config with custom template."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.metadata_ = {}
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"

        mock_template = MagicMock()
        mock_template.https_template = "server { listen 443 ssl; server_name {{ domain }}; }"

        with patch("custom_domain.services.nginx.template_service") as mock_ts:
            mock_ts.render_template.return_value = (
                "server { listen 443 ssl; server_name test.example.com; }"
            )
            config = await nginx_manager.generate_https_config(mock_domain, mock_template)
            assert "test.example.com" in config

    @pytest.mark.asyncio
    async def test_generate_https_config_no_template(self):
        """Test generating HTTPS config without template."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.metadata_ = {}
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"

        with patch("custom_domain.services.nginx.template_service") as mock_ts:
            mock_ts.render_default_https.return_value = "server { listen 443 ssl; }"
            config = await nginx_manager.generate_https_config(mock_domain, None)
            assert "server" in config

    @pytest.mark.asyncio
    async def test_write_config(self):
        """The configuration is staged, then installed by the privileged helper."""
        seen = {}

        async def fake_run(command, argument=None):
            staged = Path(settings.privileged_staging_dir) / "custom-domain-test.example.com.conf"
            seen["content"] = staged.read_text()
            seen["call"] = (command, argument)
            return PrivilegedResult(returncode=0)

        with patch("custom_domain.services.nginx.run_privileged", side_effect=fake_run):
            await nginx_manager.write_config("test.example.com", "server { listen 80; }")

        assert seen["call"] == ("write-config", "test.example.com")
        assert seen["content"] == "server { listen 80; }"
        # the staged copy does not outlive the call
        assert list(Path(settings.privileged_staging_dir).iterdir()) == []

    @pytest.mark.asyncio
    async def test_write_config_failure(self):
        """A failing helper raises with its message and still cleans the staged file."""
        result = PrivilegedResult(returncode=1, stderr="Permission denied")
        with (
            patch("custom_domain.services.nginx.run_privileged", return_value=result),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await nginx_manager.write_config("test.example.com", "server { listen 80; }")
        assert "Permission denied" in str(exc_info.value)
        assert list(Path(settings.privileged_staging_dir).iterdir()) == []

    @pytest.mark.asyncio
    async def test_write_config_requires_helper_settings(self, monkeypatch):
        """Nothing is staged or run when the deployment is not configured."""
        monkeypatch.setattr(settings, "privileged_staging_dir", "")
        with pytest.raises(ConfigurationError, match="PRIVILEGED_STAGING_DIR"):
            await nginx_manager.write_config("test.example.com", "server {}")

    @pytest.mark.asyncio
    async def test_remove_config(self):
        """Removal is delegated to the helper, which owns the path."""
        mock_run = AsyncMock(return_value=PrivilegedResult(returncode=0))
        with patch("custom_domain.services.nginx.run_privileged", mock_run):
            await nginx_manager.remove_config("test.example.com")
        mock_run.assert_awaited_once_with("remove-config", "test.example.com")

    @pytest.mark.asyncio
    async def test_remove_config_failure(self):
        """Test removing config file failure."""
        result = PrivilegedResult(returncode=1, stderr="Permission denied")
        with (
            patch("custom_domain.services.nginx.run_privileged", return_value=result),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await nginx_manager.remove_config("test.example.com")
        assert "Permission denied" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reload(self):
        """Reload tests the configuration first, then reloads."""
        mock_run = AsyncMock(return_value=PrivilegedResult(returncode=0))
        with patch("custom_domain.services.nginx.run_privileged", mock_run):
            await nginx_manager.reload()
        assert [c.args for c in mock_run.await_args_list] == [("test-nginx",), ("reload-nginx",)]

    @pytest.mark.asyncio
    async def test_reload_failure_config_test(self):
        """Test nginx reload failure due to config test."""
        mock_run = AsyncMock(return_value=PrivilegedResult(returncode=1, stderr="config error"))
        with (
            patch("custom_domain.services.nginx.run_privileged", mock_run),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await nginx_manager.reload()
        assert "config error" in str(exc_info.value)
        mock_run.assert_awaited_once_with("test-nginx")

    @pytest.mark.asyncio
    async def test_reload_failure_systemctl(self):
        """Test nginx reload failure due to systemctl."""
        results = [
            PrivilegedResult(returncode=0),
            PrivilegedResult(returncode=1, stderr="reload failed"),
        ]
        with (
            patch("custom_domain.services.nginx.run_privileged", side_effect=results),
            pytest.raises(RuntimeError) as exc_info,
        ):
            await nginx_manager.reload()
        assert "reload failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_test_config(self):
        """Test nginx config test."""
        with patch(
            "custom_domain.services.nginx.run_privileged",
            return_value=PrivilegedResult(returncode=0),
        ):
            result, error = await nginx_manager.test_config()
        assert result is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_test_config_failure(self):
        """Test nginx config test failure."""
        result = PrivilegedResult(returncode=1, stderr="config error")
        with patch("custom_domain.services.nginx.run_privileged", return_value=result):
            ok, error = await nginx_manager.test_config()
        assert ok is False
        assert "config error" in error

    def test_get_template_context(self):
        """Test building template context."""
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        mock_domain.upstream_target = "unix:/var/run/app.sock"
        mock_domain.metadata_ = {"key": "value"}
        mock_domain.client_id = "test-client"
        mock_domain.owner_id = "org_123"

        context = nginx_manager._get_template_context(mock_domain)

        assert context["domain"] == "test.example.com"
        assert context["upstream_target"] == "unix:/var/run/app.sock"
        assert context["client_id"] == "test-client"
        assert context["owner_id"] == "org_123"
        assert context["metadata"] == {"key": "value"}
        assert context["ssl_certificate"] == "/srv/letsencrypt/live/test.example.com/fullchain.pem"
        assert (
            context["ssl_certificate_key"] == "/srv/letsencrypt/live/test.example.com/privkey.pem"
        )
        assert context["certbot_webroot"] == "/srv/acme"

    @pytest.mark.parametrize("setting", ["letsencrypt_dir", "certbot_webroot"])
    def test_get_template_context_requires_paths(self, monkeypatch, setting):
        """Rendering fails with the variable name when a deployment path is missing."""
        monkeypatch.setattr(settings, setting, "")
        mock_domain = MagicMock()
        mock_domain.domain = "test.example.com"
        with pytest.raises(ConfigurationError, match=setting.upper()):
            nginx_manager._get_template_context(mock_domain)
