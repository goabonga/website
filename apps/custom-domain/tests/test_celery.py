# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/celery.py."""

import importlib

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
