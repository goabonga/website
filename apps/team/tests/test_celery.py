# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery configuration module."""

from unittest.mock import patch

from team.celery import on_celery_setup_logging


class TestOnCelerySetupLogging:
    @patch("team.celery.setup_logging")
    @patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"})
    def test_uses_env_log_level(self, mock_setup_logging):
        on_celery_setup_logging()
        mock_setup_logging.assert_called_once_with(level="DEBUG")

    @patch("team.celery.setup_logging")
    @patch.dict("os.environ", {}, clear=True)
    def test_defaults_to_info(self, mock_setup_logging):
        on_celery_setup_logging()
        mock_setup_logging.assert_called_once_with(level="INFO")


class TestCeleryAppConfig:
    def test_celery_app_name(self):
        from team.celery import celery_app

        assert celery_app.main == "team"

    def test_celery_default_queue(self):
        from team.celery import celery_app

        assert celery_app.conf.task_default_queue == "team"

    def test_beat_schedule_has_dispatch_tasks(self):
        from team.celery import celery_app

        assert "dispatch-tasks-every-5-minutes" in celery_app.conf.beat_schedule

    def test_beat_schedule_has_cleanup_logs(self):
        from team.celery import celery_app

        assert "cleanup-old-logs-daily" in celery_app.conf.beat_schedule

    def test_beat_schedule_has_summarize_memory(self):
        from team.celery import celery_app

        assert "summarize-memory-hourly" in celery_app.conf.beat_schedule
