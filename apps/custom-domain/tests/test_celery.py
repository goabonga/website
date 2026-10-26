# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/celery.py."""

import importlib

import pytest
from custom_domain.config import settings


def reload_celery(monkeypatch, **values):
    """Reload the Celery module with some settings changed."""
    import custom_domain.celery as celery_module

    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return importlib.reload(celery_module)


class TestQueue:
    """Every task is published to the queue the worker consumes."""

    def test_default_queue_is_the_documented_one(self):
        from custom_domain.celery import celery_app

        assert celery_app.conf.task_default_queue == "custom-domain"

    def test_queue_name_is_a_setting(self, monkeypatch):
        module = reload_celery(monkeypatch, celery_queue="edge-queue")
        try:
            assert module.celery_app.conf.task_default_queue == "edge-queue"
            assert module.celery_app.conf.task_routes == {
                "custom_domain.tasks.*": {"queue": "edge-queue"}
            }
        finally:
            monkeypatch.undo()
            importlib.reload(module)

    def test_every_task_is_routed_to_the_queue(self):
        import custom_domain.tasks  # noqa: F401
        from custom_domain.celery import celery_app

        names = [name for name in celery_app.tasks if name.startswith("custom_domain.tasks.")]
        assert names, "no task registered"
        for name in names:
            route = celery_app.amqp.router.route({}, name)
            assert route["queue"].name == settings.celery_queue, name

    def test_time_limits_are_settings(self, monkeypatch):
        module = reload_celery(
            monkeypatch,
            celery_task_soft_time_limit_seconds=11,
            celery_task_time_limit_seconds=22,
        )
        try:
            assert module.celery_app.conf.task_soft_time_limit == 11
            assert module.celery_app.conf.task_time_limit == 22
        finally:
            monkeypatch.undo()
            importlib.reload(module)


class TestBeatSchedule:
    """Periodic tasks are published to the worker's queue too."""

    def test_every_entry_targets_the_queue(self):
        from custom_domain.celery import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "check-pending-domains" in schedule
        for name, entry in schedule.items():
            assert entry["options"] == {"queue": settings.celery_queue}, name

    def test_dns_scan_interval_is_a_setting(self, monkeypatch):
        module = reload_celery(monkeypatch, dns_check_interval_minutes=7)
        try:
            entry = module.celery_app.conf.beat_schedule["check-pending-domains"]
            assert entry["schedule"].minute == set(range(0, 60, 7))
        finally:
            monkeypatch.undo()
            importlib.reload(module)

    def test_beat_entries_follow_a_custom_queue(self, monkeypatch):
        module = reload_celery(monkeypatch, celery_queue="edge-queue")
        try:
            for entry in module.celery_app.conf.beat_schedule.values():
                assert entry["options"] == {"queue": "edge-queue"}
        finally:
            monkeypatch.undo()
            importlib.reload(module)


class TestMaintenanceSchedule:
    """The maintenance entries come from settings, not from values in the code."""

    EXPECTED = {
        "check-certificate-expiry": "custom_domain.tasks.maintenance.check_certificate_expiry",
        "check-domain-health": "custom_domain.tasks.maintenance.check_domain_health",
        "cleanup-stale-domains": "custom_domain.tasks.maintenance.cleanup_stale_domains",
        "purge-deleted-domains": "custom_domain.tasks.maintenance.purge_deleted_domains",
    }

    def test_entries_are_scheduled(self):
        from custom_domain.celery import celery_app

        schedule = celery_app.conf.beat_schedule
        for name, task in self.EXPECTED.items():
            assert schedule[name]["task"] == task

    def test_documented_defaults(self):
        from custom_domain.celery import celery_app

        schedule = celery_app.conf.beat_schedule
        expiry = schedule["check-certificate-expiry"]["schedule"]
        assert (expiry.hour, expiry.minute) == ({2}, {0})
        purge = schedule["purge-deleted-domains"]["schedule"]
        assert (purge.hour, purge.minute, purge.day_of_week) == ({5}, {0}, {0})
        health = schedule["check-domain-health"]["schedule"]
        assert health.minute == {30}

    def test_cron_settings_are_honoured(self, monkeypatch):
        module = reload_celery(
            monkeypatch,
            certificate_expiry_check_cron="15 3 * * *",
            stale_cleanup_cron="45 1 * * 1",
            purge_deleted_cron="0 0 1 * *",
            domain_health_check_interval_hours=6,
            domain_health_check_minute=10,
        )
        try:
            schedule = module.celery_app.conf.beat_schedule
            assert schedule["check-certificate-expiry"]["schedule"].minute == {15}
            assert schedule["check-certificate-expiry"]["schedule"].hour == {3}
            assert schedule["cleanup-stale-domains"]["schedule"].day_of_week == {1}
            assert schedule["purge-deleted-domains"]["schedule"].day_of_month == {1}
            assert schedule["check-domain-health"]["schedule"].hour == {0, 6, 12, 18}
            assert schedule["check-domain-health"]["schedule"].minute == {10}
        finally:
            monkeypatch.undo()
            importlib.reload(module)


class TestFromCron:
    """Cron expressions are validated."""

    def test_five_fields(self):
        from custom_domain.celery import from_cron

        schedule = from_cron("5 4 3 2 1")
        assert schedule.minute == {5}
        assert schedule.hour == {4}
        assert schedule.day_of_month == {3}
        assert schedule.month_of_year == {2}
        assert schedule.day_of_week == {1}

    @pytest.mark.parametrize("expression", ["", "* * * *", "* * * * * *", "daily"])
    def test_wrong_field_count_is_refused(self, expression):
        from custom_domain.celery import from_cron

        with pytest.raises(ValueError, match="5 cron fields"):
            from_cron(expression)
