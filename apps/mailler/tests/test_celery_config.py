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

    def test_beat_schedule_contains_core_tasks(self):
        schedule = celery_app.conf.beat_schedule
        assert "requeue-stuck-emails" in schedule
        assert "process-scheduled-emails" in schedule
        assert "cleanup-old-emails" in schedule
        assert "aggregate-daily-stats" in schedule
        assert "check-scheduled-campaigns" in schedule

    def test_beat_schedule_task_names(self):
        schedule = celery_app.conf.beat_schedule
        assert (
            schedule["requeue-stuck-emails"]["task"]
            == "mailler.tasks.scheduler.requeue_stuck_emails"
        )
        assert (
            schedule["process-scheduled-emails"]["task"]
            == "mailler.tasks.scheduler.process_scheduled_emails"
        )
        assert (
            schedule["cleanup-old-emails"]["task"] == "mailler.tasks.scheduler.cleanup_old_emails"
        )
        assert (
            schedule["aggregate-daily-stats"]["task"]
            == "mailler.tasks.scheduler.aggregate_daily_stats"
        )
        assert (
            schedule["check-scheduled-campaigns"]["task"]
            == "mailler.tasks.scheduler.check_scheduled_campaigns"
        )
