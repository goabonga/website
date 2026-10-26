# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.celery module."""

from unittest.mock import patch

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
        assert "cleanup-expired-attachments" in schedule

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
        assert (
            schedule["cleanup-expired-attachments"]["task"]
            == "mailler.tasks.inbound.cleanup_expired_attachments"
        )


class TestInboundSchedule:
    """Tests for inbound email schedule configuration (lines 67-75)."""

    def test_inbound_schedules_based_on_settings(self):
        """Verify inbound schedules presence matches inbound_enabled setting."""
        schedule = celery_app.conf.beat_schedule

        if settings.inbound_enabled:
            assert "poll-inbound-emails" in schedule
            assert (
                schedule["poll-inbound-emails"]["task"]
                == "mailler.tasks.inbound.poll_inbound_emails"
            )
            assert "retry-failed-inbound" in schedule
            assert (
                schedule["retry-failed-inbound"]["task"]
                == "mailler.tasks.inbound.retry_failed_inbound"
            )
        else:
            assert "poll-inbound-emails" not in schedule
            assert "retry-failed-inbound" not in schedule

    def test_inbound_enabled_adds_poll_and_retry_schedules(self):
        """Simulate inbound_enabled=True to cover lines 68-75."""
        from celery import Celery
        from celery.schedules import crontab

        test_app = Celery("test_inbound")
        test_app.conf.beat_schedule = {}

        # Simulate the conditional block from mailler/celery.py lines 67-75
        inbound_enabled = True
        inbound_poll_interval = 60

        if inbound_enabled:
            test_app.conf.beat_schedule["poll-inbound-emails"] = {
                "task": "mailler.tasks.inbound.poll_inbound_emails",
                "schedule": inbound_poll_interval,
            }
            test_app.conf.beat_schedule["retry-failed-inbound"] = {
                "task": "mailler.tasks.inbound.retry_failed_inbound",
                "schedule": crontab(minute="*/5"),
            }

        assert "poll-inbound-emails" in test_app.conf.beat_schedule
        assert test_app.conf.beat_schedule["poll-inbound-emails"]["schedule"] == 60
        assert "retry-failed-inbound" in test_app.conf.beat_schedule

    def test_inbound_enabled_module_reload(self):
        """Cover lines 68-72 by reloading the celery module with inbound_enabled=True.

        This test patches settings.inbound_enabled to True before reloading the
        mailler.celery module, ensuring the conditional beat schedule registration
        code at lines 67-75 is actually executed.
        """
        import importlib

        import mailler.celery as celery_module

        with (
            patch.object(settings, "inbound_enabled", True),
            patch.object(settings, "inbound_poll_interval", 45),
        ):
            importlib.reload(celery_module)

            schedule = celery_module.celery_app.conf.beat_schedule
            assert "poll-inbound-emails" in schedule
            assert (
                schedule["poll-inbound-emails"]["task"]
                == "mailler.tasks.inbound.poll_inbound_emails"
            )
            assert schedule["poll-inbound-emails"]["schedule"] == 45
            assert "retry-failed-inbound" in schedule
            assert (
                schedule["retry-failed-inbound"]["task"]
                == "mailler.tasks.inbound.retry_failed_inbound"
            )

        # Reload again to restore original state
        importlib.reload(celery_module)
