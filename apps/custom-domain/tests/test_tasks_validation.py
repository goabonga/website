# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/tasks/validation.py."""

from unittest.mock import AsyncMock, patch

from custom_domain.tasks.validation import validate_nginx_template


class TestValidateNginxTemplate:
    """The task runs the helper-based check and returns a plain dictionary."""

    def test_valid(self):
        with patch("custom_domain.tasks.validation.template_service") as mock_service:
            mock_service.validate_nginx_syntax = AsyncMock(return_value=(True, ""))
            assert validate_nginx_template("server {}") == {"valid": True, "error": ""}
        mock_service.validate_nginx_syntax.assert_awaited_once_with("server {}")

    def test_invalid(self):
        with patch("custom_domain.tasks.validation.template_service") as mock_service:
            mock_service.validate_nginx_syntax = AsyncMock(return_value=(False, "bad"))
            assert validate_nginx_template("x") == {"valid": False, "error": "bad"}

    def test_is_routed_to_the_worker_queue(self):
        from custom_domain.celery import celery_app
        from custom_domain.config import settings

        route = celery_app.amqp.router.route({}, validate_nginx_template.name)
        assert route["queue"].name == settings.celery_queue
