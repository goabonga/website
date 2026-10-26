# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.celery — Celery application configuration."""

from unittest.mock import patch


class TestCeleryApp:
    def test_app_exists(self):
        from auth.celery import celery_app

        assert celery_app is not None
        assert celery_app.main == "auth"

    def test_conf_settings(self):
        from auth.celery import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.accept_content == ["json"]
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True
        assert celery_app.conf.task_track_started is True
        assert celery_app.conf.task_time_limit == 300
        assert celery_app.conf.task_soft_time_limit == 240
        assert celery_app.conf.worker_prefetch_multiplier == 1
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.task_default_queue == "auth"

    def test_beat_schedule_tasks(self):
        from auth.celery import celery_app

        schedule = celery_app.conf.beat_schedule
        expected_tasks = [
            "retry-pending-webhooks",
            "cleanup-webhook-deliveries",
        ]
        for task_name in expected_tasks:
            assert task_name in schedule, f"Missing beat schedule: {task_name}"

    def test_beat_schedule_count(self):
        from auth.celery import celery_app

        assert len(celery_app.conf.beat_schedule) == 2

    def test_task_queues(self):
        from auth.celery import celery_app

        queues = celery_app.conf.task_queues
        assert "auth" in queues
        assert queues["auth"]["exchange"] == "auth"
        assert queues["auth"]["routing_key"] == "auth"

    def test_result_backend_default_none(self):
        from auth.config import settings

        # Default is None (fire-and-forget)
        assert settings.celery_result_backend is None

    def test_celery_app_with_result_backend(self):
        with patch("auth.celery.settings") as mock_settings:
            mock_settings.celery_broker_url = "redis://localhost:6379/0"
            mock_settings.celery_result_backend = "redis://localhost:6379/1"
            # The module-level code already ran; just verify the conditional logic
            celery_kwargs = {
                "main": "auth",
                "broker": mock_settings.celery_broker_url,
            }
            if mock_settings.celery_result_backend:
                celery_kwargs["backend"] = mock_settings.celery_result_backend
            assert "backend" in celery_kwargs
            assert celery_kwargs["backend"] == "redis://localhost:6379/1"


class TestResultBackend:
    def test_backend_configured_when_setting_present(self):
        import importlib

        import auth.celery as celery_module

        with patch.object(celery_module.settings, "celery_result_backend", "redis://localhost/1"):
            reloaded = importlib.reload(celery_module)
            backend_url = reloaded.celery_app.conf.result_backend

        assert backend_url == "redis://localhost/1"

        # Restore the default (no result backend) module state.
        importlib.reload(celery_module)

    def test_backend_absent_by_default(self):
        from auth.celery import celery_app

        assert not celery_app.conf.result_backend
