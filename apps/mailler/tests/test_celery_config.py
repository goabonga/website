# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.celery module."""

from mailler.celery import celery_app
from mailler.config import settings


class TestCeleryConfig:
    """Tests for Celery application configuration."""

    def test_app_name(self):
        assert celery_app.main == "mailler"

    def test_serializer_settings(self):
        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content
        assert celery_app.conf.result_serializer == "json"

    def test_timezone_settings(self):
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True

    def test_task_tracking(self):
        assert celery_app.conf.task_track_started is True

    def test_task_time_limits(self):
        assert celery_app.conf.task_time_limit == 300
        assert celery_app.conf.task_soft_time_limit == 270

    def test_worker_settings(self):
        assert celery_app.conf.worker_prefetch_multiplier == 1
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True

    def test_broker_settings(self):
        assert celery_app.conf.broker_connection_retry_on_startup is True

    def test_default_queue(self):
        assert celery_app.conf.task_default_queue == settings.celery_queue
        assert settings.celery_queue in celery_app.conf.task_queues
