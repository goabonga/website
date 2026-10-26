# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Celery configuration module."""

from unittest.mock import patch

from billing.celery import celery_app, on_celery_setup_logging
from billing.config import settings


class TestOnCelerySetupLogging:
    @patch("billing.celery.setup_logging")
    @patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"})
    def test_uses_env_log_level(self, mock_setup_logging):
        on_celery_setup_logging()
        mock_setup_logging.assert_called_once_with(level="DEBUG")

    @patch("billing.celery.setup_logging")
    @patch.dict("os.environ", {}, clear=True)
    def test_defaults_to_info(self, mock_setup_logging):
        on_celery_setup_logging()
        mock_setup_logging.assert_called_once_with(level="INFO")


class TestCeleryConfiguration:
    """Queue, time zone, limits and beat schedule come from the settings."""

    def test_queue_timezone_and_limit(self):
        conf = celery_app.conf

        assert conf.task_default_queue == settings.celery_queue
        assert list(conf.task_queues) == [settings.celery_queue]
        assert conf.timezone == settings.celery_timezone
        assert conf.task_time_limit == settings.celery_task_time_limit

    def test_beat_schedule(self):
        schedule = celery_app.conf.beat_schedule

        report = schedule["report-pending-usage"]
        assert report["schedule"] == settings.usage_report_interval
        assert report["kwargs"] == {"batch_size": settings.usage_report_batch_size}
        cleanup = schedule["cleanup-old-usage-events"]
        assert cleanup["schedule"] == settings.usage_cleanup_interval
        assert cleanup["kwargs"] == {"days_old": settings.usage_retention_days}
        assert schedule["sync-products-to-stripe"]["schedule"] == settings.stripe_sync_interval

    def test_defaults_are_neutral(self):
        from billing.config import Settings

        defaults = Settings(_env_file=None)

        assert defaults.celery_timezone == "UTC"
        assert defaults.celery_queue == "billing"
        assert defaults.usage_retention_days == 90
