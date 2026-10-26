# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing.tasks.webhook_tasks (delivery of SaaS notifications, with retries)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from billing.config import Settings, settings
from billing.services.saas_webhook import WebhookDeliveryError
from billing.tasks import webhook_tasks
from billing.tasks.webhook_tasks import (
    _deliver,
    deliver_saas_webhook,
    retry_delay,
    should_retry,
)

EVENT = {"id": "evt-1", "type": "subscription.updated", "data": {}}


@pytest.fixture(autouse=True)
def _retry_settings(monkeypatch):
    monkeypatch.setattr(settings, "saas_webhook_max_attempts", 4)
    monkeypatch.setattr(settings, "saas_webhook_backoff_seconds", 10.0)
    monkeypatch.setattr(settings, "saas_webhook_backoff_factor", 3.0)
    monkeypatch.setattr(settings, "saas_webhook_backoff_max_seconds", 100.0)


def _failing(retryable: bool) -> WebhookDeliveryError:
    return WebhookDeliveryError("receiver answered 503", retryable=retryable)


class TestSettings:
    def test_defaults(self):
        defaults = Settings(_env_file=None)

        assert defaults.saas_webhook_max_attempts == 5
        assert defaults.saas_webhook_backoff_seconds == 30.0
        assert defaults.saas_webhook_backoff_factor == 2.0
        assert defaults.saas_webhook_backoff_max_seconds == 3600.0

    def test_overrides(self):
        custom = Settings(
            _env_file=None, saas_webhook_max_attempts=9, saas_webhook_backoff_seconds=1
        )

        assert (custom.saas_webhook_max_attempts, custom.saas_webhook_backoff_seconds) == (9, 1.0)


class TestRetryDelay:
    def test_grows_with_the_factor_then_is_capped(self):
        assert [retry_delay(n) for n in range(5)] == [10.0, 30.0, 90.0, 100.0, 100.0]

    def test_a_factor_of_one_keeps_a_constant_delay(self, monkeypatch):
        monkeypatch.setattr(settings, "saas_webhook_backoff_factor", 1.0)

        assert {retry_delay(n) for n in range(4)} == {10.0}


class TestShouldRetry:
    def test_retryable_failures_are_retried_until_the_last_attempt(self):
        error = _failing(True)

        # 4 attempts in total: the first one plus 3 retries
        assert [should_retry(error, retries) for retries in range(5)] == [
            True,
            True,
            True,
            False,
            False,
        ]

    def test_other_failures_are_final(self):
        assert should_retry(_failing(False), 0) is False

    def test_a_single_attempt_disables_the_retries(self, monkeypatch):
        monkeypatch.setattr(settings, "saas_webhook_max_attempts", 1)

        assert should_retry(_failing(True), 0) is False


class TestDeliver:
    @pytest.mark.asyncio
    async def test_loads_the_saas_app_and_sends_with_a_fresh_client(self):
        saas_app = MagicMock()
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(webhook_tasks, "async_session_factory", factory),
            patch.object(webhook_tasks, "get_saas_app_by_id", AsyncMock(return_value=saas_app)),
            patch.object(webhook_tasks, "new_http_client", return_value=client),
            patch.object(webhook_tasks, "deliver_event", AsyncMock()) as deliver,
        ):
            await _deliver("saas-1", EVENT)

        deliver.assert_awaited_once_with(saas_app, EVENT, client=client)

    @pytest.mark.asyncio
    async def test_a_deleted_saas_app_is_a_final_failure(self):
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(webhook_tasks, "async_session_factory", factory),
            patch.object(webhook_tasks, "get_saas_app_by_id", AsyncMock(return_value=None)),
            pytest.raises(WebhookDeliveryError) as exc_info,
        ):
            await _deliver("gone", EVENT)

        assert exc_info.value.retryable is False


class TestDeliverSaasWebhookTask:
    """Run eagerly: a retry re-runs the task at once, the countdown is ignored."""

    def test_delivered_at_the_first_attempt(self):
        with patch.object(webhook_tasks, "_deliver", AsyncMock()) as deliver:
            result = deliver_saas_webhook.apply(args=["saas-1", EVENT]).get()

        assert result == {"event_id": "evt-1", "delivered": True, "attempts": 1}
        deliver.assert_awaited_once_with("saas-1", EVENT)

    def test_final_failure_is_not_retried(self):
        deliver = AsyncMock(side_effect=_failing(False))
        with patch.object(webhook_tasks, "_deliver", deliver):
            result = deliver_saas_webhook.apply(args=["saas-1", EVENT]).get()

        assert result == {"event_id": "evt-1", "delivered": False, "attempts": 1}
        assert deliver.await_count == 1

    def test_retryable_failure_is_retried_until_it_succeeds(self):
        deliver = AsyncMock(side_effect=[_failing(True), _failing(True), None])
        with patch.object(webhook_tasks, "_deliver", deliver):
            result = deliver_saas_webhook.apply(args=["saas-1", EVENT]).get()

        assert result["delivered"] is True
        assert result["attempts"] == 3
        assert deliver.await_count == 3

    def test_gives_up_after_the_configured_number_of_attempts(self):
        deliver = AsyncMock(side_effect=_failing(True))
        with patch.object(webhook_tasks, "_deliver", deliver):
            result = deliver_saas_webhook.apply(args=["saas-1", EVENT]).get()

        assert result == {"event_id": "evt-1", "delivered": False, "attempts": 4}
        assert deliver.await_count == 4

    def test_every_attempt_sends_the_same_event(self):
        deliver = AsyncMock(side_effect=[_failing(True), None])
        with patch.object(webhook_tasks, "_deliver", deliver):
            deliver_saas_webhook.apply(args=["saas-1", EVENT]).get()

        assert [call.args for call in deliver.await_args_list] == [("saas-1", EVENT)] * 2

    def test_the_retry_is_scheduled_with_the_backoff(self):
        deliver = AsyncMock(side_effect=_failing(True))
        with (
            patch.object(webhook_tasks, "_deliver", deliver),
            patch.object(deliver_saas_webhook, "retry", side_effect=RuntimeError("stop")) as retry,
            pytest.raises(RuntimeError),
        ):
            deliver_saas_webhook.apply(args=["saas-1", EVENT], throw=True)

        assert retry.call_args.kwargs["countdown"] == 10.0

    def test_task_is_registered_on_the_billing_app_and_queue(self):
        from billing.celery import celery_app

        assert "billing.tasks.webhook_tasks.deliver_saas_webhook" in celery_app.tasks
        assert "billing.tasks.webhook_tasks" in celery_app.conf.include
