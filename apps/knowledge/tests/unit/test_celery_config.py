# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the Celery application configuration."""

from knowledge.celery import celery_app
from knowledge.config import get_settings


class TestCeleryApp:
    def test_default_queue(self):
        assert celery_app.conf.task_default_queue == "knowledge"
        assert set(celery_app.conf.task_queues) == {"knowledge"}

    def test_queue_and_limits_come_from_the_settings(self):
        settings = get_settings()
        assert celery_app.conf.task_default_queue == settings.celery_queue
        assert set(celery_app.conf.task_queues) == {settings.celery_queue}
        assert celery_app.conf.timezone == settings.celery_timezone
        assert celery_app.conf.task_time_limit == settings.celery_task_time_limit

    def test_settings_defaults(self):
        from knowledge.config import Settings

        settings = Settings(_env_file=None)
        assert settings.celery_queue == "knowledge"
        assert settings.celery_timezone == "UTC"
        assert settings.celery_task_time_limit == 300
        assert settings.deletion_check_interval == 3600.0

    def test_json_serialization(self):
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.accept_content == ["json"]

    def test_reliable_delivery_settings(self):
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_task_module_is_registered(self):
        celery_app.loader.import_default_modules()
        assert "knowledge.tasks.send_email" in celery_app.tasks


class TestBeatSchedule:
    def test_deletion_tasks_run_at_the_configured_interval(self):
        schedule = celery_app.conf.beat_schedule
        deletions = schedule["process-scheduled-deletions"]
        reminders = schedule["send-deletion-reminders"]
        assert deletions["task"] == "knowledge.tasks.process_scheduled_deletions"
        assert reminders["task"] == "knowledge.tasks.send_deletion_reminders"
        interval = get_settings().deletion_check_interval
        assert deletions["schedule"] == interval
        assert reminders["schedule"] == interval

    def test_custom_domains_are_reconciled_at_the_configured_interval(self):
        entry = celery_app.conf.beat_schedule["reconcile-custom-domains"]
        assert entry["task"] == "knowledge.tasks.custom_domain.reconcile_custom_domains"
        assert entry["schedule"] == get_settings().custom_domain_reconcile_interval

    def test_every_scheduled_task_is_registered(self):
        celery_app.loader.import_default_modules()
        for entry in celery_app.conf.beat_schedule.values():
            assert entry["task"] in celery_app.tasks
