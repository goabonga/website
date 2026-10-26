# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.celery configuration."""

from unittest.mock import patch

from celery import Celery


class TestCeleryConfiguration:
    """Tests for celery_app configuration."""

    @patch("backend.config.settings")
    def test_celery_app_is_celery_instance(self, _mock_settings):
        """celery_app is a Celery instance."""
        from backend.celery import celery_app

        assert isinstance(celery_app, Celery)

    @patch("backend.config.settings")
    def test_celery_task_serializer_is_json(self, _mock_settings):
        """celery_app.conf.task_serializer is 'json'."""
        from backend.celery import celery_app

        assert celery_app.conf.task_serializer == "json"

    @patch("backend.config.settings")
    def test_celery_default_queue_is_backend(self, _mock_settings):
        """celery_app.conf.task_default_queue is 'backend'."""
        from backend.celery import celery_app

        assert celery_app.conf.task_default_queue == "backend"
