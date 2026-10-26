# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/template.py."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_domain.config import settings
from custom_domain.services.privileged import PrivilegedResult
from custom_domain.services.template import (
    TemplateService,
    TemplateValidationResult,
    template_service,
)


class TestTemplateValidationResult:
    """Tests for TemplateValidationResult dataclass."""

    def test_create_valid_result(self):
        """Test creating a valid result."""
        result = TemplateValidationResult(
            valid=True,
            errors=[],
            rendered_output="server { listen 80; }",
        )
        assert result.valid is True
        assert result.rendered_output is not None

    def test_create_invalid_result(self):
        """Test creating an invalid result."""
        result = TemplateValidationResult(
            valid=False,
            errors=["Syntax error at line 1"],
        )
        assert result.valid is False
        assert len(result.errors) == 1


class TestTemplateService:
    """Tests for TemplateService."""

    def test_init(self):
        """Test service initialization."""
        with patch("custom_domain.services.template.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            service = TemplateService()
            assert service.jinja_env is not None

    def test_render_template(self):
        """Test rendering a template from source."""
        service = template_service
        result = service.render_template(
            "Hello {{ name }}!",
            {"name": "World"},
        )
        assert result == "Hello World!"

    def test_render_template_with_complex_context(self):
        """Test rendering template with complex context."""
        service = template_service
        result = service.render_template(
            "server { server_name {{ domain }}; upstream {{ upstream }}; }",
            {"domain": "test.example.com", "upstream": "backend"},
        )
        assert "test.example.com" in result
        assert "backend" in result

    def test_validate_template_valid(self):
        """Test validating a valid template."""
        service = template_service
        result = service.validate_template("server { listen {{ port }}; }")
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_template_with_context(self):
        """Test validating template with test context."""
        service = template_service
        result = service.validate_template(
            "server { listen {{ port }}; }",
            {"port": "80"},
        )
        assert result.valid is True
        assert result.rendered_output == "server { listen 80; }"

    def test_validate_template_syntax_error(self):
        """Test validating template with syntax error."""
        service = template_service
        result = service.validate_template("{{ invalid syntax }")
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_template_render_error(self):
        """Test validating template that fails to render."""
        service = template_service
        result = service.validate_template(
            "{{ undefined_var.method() }}",
            {"other": "value"},
        )
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_get_template_by_id(self):
        """Test getting template by ID."""
        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.slug = "test-template"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = template_service
        template = await service.get_template(mock_db, 1)
        assert template is not None
        assert template.id == 1

    @pytest.mark.asyncio
    async def test_get_template_default(self):
        """Test getting default template."""
        mock_template = MagicMock()
        mock_template.is_default = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = template_service
        template = await service.get_template(mock_db)
        assert template is not None
        assert template.is_default is True

    @pytest.mark.asyncio
    async def test_get_template_not_found(self):
        """Test getting non-existent template."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = template_service
        template = await service.get_template(mock_db, 99999)
        assert template is None

    @pytest.mark.asyncio
    async def test_validate_nginx_syntax_valid(self):
        """The text is staged under a one-time token and checked by the helper."""
        service = template_service
        config = "server { listen 80; server_name test.example.com; }"
        seen = {}

        async def fake_run(command, argument=None):
            staged = Path(settings.privileged_staging_dir) / f"validate-{argument}.conf"
            seen["content"] = staged.read_text()
            seen["call"] = (command, argument)
            return PrivilegedResult(returncode=0)

        with patch("custom_domain.services.template.run_privileged", side_effect=fake_run):
            valid, error = await service.validate_nginx_syntax(config)

        assert valid is True
        assert error == ""
        command, token = seen["call"]
        assert command == "check-snippet"
        assert len(token) == 32
        assert seen["content"] == config
        assert list(Path(settings.privileged_staging_dir).iterdir()) == []

    @pytest.mark.asyncio
    async def test_validate_nginx_syntax_invalid(self):
        """Test validating invalid nginx syntax."""
        service = template_service
        result = PrivilegedResult(returncode=1, stderr="syntax error")

        with patch("custom_domain.services.template.run_privileged", return_value=result):
            valid, error = await service.validate_nginx_syntax("invalid { config")

        assert valid is False
        assert "syntax error" in error
        assert list(Path(settings.privileged_staging_dir).iterdir()) == []

    @pytest.mark.asyncio
    async def test_validate_nginx_syntax_exception(self):
        """Test nginx validation with exception."""
        service = template_service

        with patch(
            "custom_domain.services.template.run_privileged",
            side_effect=Exception("Command failed"),
        ):
            valid, error = await service.validate_nginx_syntax("server {}")

        assert valid is False
        assert "Command failed" in error

    @pytest.mark.asyncio
    async def test_validate_nginx_syntax_not_configured(self, monkeypatch):
        """A missing helper setting is reported, not raised."""
        monkeypatch.setattr(settings, "privileged_staging_dir", "")

        valid, error = await template_service.validate_nginx_syntax("server {}")

        assert valid is False
        assert "PRIVILEGED_STAGING_DIR" in error

    def test_render_default_http(self):
        """Test rendering the default HTTP template."""
        service = template_service
        context = {
            "domain": "test.example.com",
            "upstream": "backend",
            "webroot": "/var/www/certbot",
        }

        with patch.object(service.jinja_env, "get_template") as mock_get:
            mock_template = MagicMock()
            mock_template.render.return_value = "server { listen 80; }"
            mock_get.return_value = mock_template

            result = service.render_default_http(context)
            assert result == "server { listen 80; }"
            mock_get.assert_called_once_with(service.default_http_template)

    def test_render_default_https(self):
        """Test rendering the default HTTPS template."""
        service = template_service
        context = {
            "domain": "test.example.com",
            "upstream": "backend",
            "ssl_cert": "/etc/letsencrypt/live/test.example.com/fullchain.pem",
            "ssl_key": "/etc/letsencrypt/live/test.example.com/privkey.pem",
        }

        with patch.object(service.jinja_env, "get_template") as mock_get:
            mock_template = MagicMock()
            mock_template.render.return_value = "server { listen 443 ssl; }"
            mock_get.return_value = mock_template

            result = service.render_default_https(context)
            assert result == "server { listen 443 ssl; }"
            mock_get.assert_called_once_with(service.default_https_template)

    def test_validate_template_generic_exception(self):
        """Test validating template with generic exception (not syntax error)."""
        service = template_service

        # The Template class is imported inside the validate_template function from jinja2
        with patch("jinja2.Template") as mock_template_class:
            mock_template_class.side_effect = RuntimeError("Unexpected error")

            result = service.validate_template("server {}")
            assert result.valid is False
            assert any("Unexpected error" in e for e in result.errors)


class TestValidateNginxSyntaxInWorker:
    """The API delegates the privileged check to a worker and waits for the answer."""

    @pytest.mark.asyncio
    async def test_returns_the_worker_answer(self):
        pending = MagicMock()
        pending.get.return_value = {"valid": False, "error": "unexpected }"}
        with patch("custom_domain.tasks.validation.validate_nginx_template") as mock_task:
            mock_task.delay.return_value = pending
            valid, error = await template_service.validate_nginx_syntax_in_worker("server {}")

        mock_task.delay.assert_called_once_with("server {}")
        assert (valid, error) == (False, "unexpected }")

    @pytest.mark.asyncio
    async def test_waits_for_the_configured_time(self, monkeypatch):
        monkeypatch.setattr(settings, "template_validation_timeout_seconds", 3)
        pending = MagicMock()
        pending.get.return_value = {"valid": True, "error": ""}
        with patch("custom_domain.tasks.validation.validate_nginx_template") as mock_task:
            mock_task.delay.return_value = pending
            await template_service.validate_nginx_syntax_in_worker("server {}")
        pending.get.assert_called_once_with(timeout=3)

    @pytest.mark.asyncio
    async def test_no_worker_is_reported_not_raised(self):
        pending = MagicMock()
        pending.get.side_effect = TimeoutError("no worker")
        with patch("custom_domain.tasks.validation.validate_nginx_template") as mock_task:
            mock_task.delay.return_value = pending
            valid, error = await template_service.validate_nginx_syntax_in_worker("server {}")
        assert valid is False
        assert "Nginx validation unavailable" in error

    @pytest.mark.asyncio
    async def test_broker_failure_is_reported_not_raised(self):
        with patch("custom_domain.tasks.validation.validate_nginx_template") as mock_task:
            mock_task.delay.side_effect = ConnectionError("broker down")
            valid, error = await template_service.validate_nginx_syntax_in_worker("server {}")
        assert valid is False
        assert "broker down" in error
