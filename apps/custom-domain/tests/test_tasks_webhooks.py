# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/tasks/webhooks.py and the dispatch in services/events.py."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from celery.exceptions import Retry
from custom_domain.config import settings
from custom_domain.models.enums import DomainStatus
from custom_domain.services.events import notify_webhook, publish_event, webhook_event_name
from custom_domain.tasks.webhooks import build_body, deliver_webhook
from custom_domain.webhook_signature import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    verify_signature,
)

SECRET = "k" * 32
URL = "https://app.example.com/hooks/domains"


def make_domain(status=DomainStatus.ACTIVE):
    domain = MagicMock()
    domain.id = uuid4()
    domain.domain = "shop.example.com"
    domain.status = status
    domain.client_id = "tenant-a"
    domain.owner_id = "org_1"
    domain.owner_type = "organization"
    domain.metadata_ = {"plan": "pro"}
    domain.error_message = None
    return domain


def make_client(**overrides):
    client = MagicMock()
    client.is_active = True
    client.webhook_url = URL
    client.webhook_secret = SECRET
    for key, value in overrides.items():
        setattr(client, key, value)
    return client


def session_for(domain, client):
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.side_effect = [domain, client]
    manager = MagicMock()
    manager.__enter__ = MagicMock(return_value=session)
    manager.__exit__ = MagicMock(return_value=False)
    return manager


def run(domain, client, *, event="domain.active", data=None, retries=0, post=None):
    """Run the delivery task with a fake database and a fake HTTP call."""
    post = post or MagicMock(return_value=httpx.Response(200))
    with (
        patch("custom_domain.tasks.webhooks.get_sync_db", return_value=session_for(domain, client)),
        patch("custom_domain.tasks.webhooks.httpx.post", post),
    ):
        deliver_webhook.push_request(retries=retries)
        try:
            result = deliver_webhook(
                str(domain.id),
                event,
                data or {"status": "active"},
                "delivery-1",
                "2026-01-01T00:00:00+00:00",
            )
        finally:
            deliver_webhook.pop_request()
    return result, post


class TestBody:
    """The delivery document."""

    def test_document(self):
        domain = make_domain()
        body = build_body(
            domain, "domain.active", {"a": 1}, "delivery-1", "2026-01-01T00:00:00+00:00"
        )
        document = json.loads(body)
        assert document == {
            "id": "delivery-1",
            "event": "domain.active",
            "created_at": "2026-01-01T00:00:00+00:00",
            "domain": {
                "id": str(domain.id),
                "domain": "shop.example.com",
                "status": "active",
                "client_id": "tenant-a",
                "owner_id": "org_1",
                "owner_type": "organization",
                "metadata": {"plan": "pro"},
                "error": None,
            },
            "data": {"a": 1},
        }

    def test_body_is_deterministic(self):
        domain = make_domain()
        args = (domain, "e", {"b": 1, "a": 2}, "i", "t")
        assert build_body(*args) == build_body(*args)
        assert b" " not in build_body(*args).replace(b"shop.example.com", b"")


class TestDelivery:
    """Sending the notification."""

    def test_signed_post_to_the_client_url(self):
        domain = make_domain()
        result, post = run(domain, make_client())

        assert result == "delivered"
        post.assert_called_once()
        assert post.call_args.args == (URL,)
        kwargs = post.call_args.kwargs
        assert kwargs["timeout"] == settings.webhook_timeout_seconds
        assert kwargs["follow_redirects"] is False
        headers = kwargs["headers"]
        assert headers[EVENT_HEADER] == "domain.active"
        assert headers[DELIVERY_HEADER] == "delivery-1"
        assert headers["Content-Type"] == "application/json"
        assert verify_signature(SECRET, kwargs["content"], headers[SIGNATURE_HEADER]) > 0
        assert json.loads(kwargs["content"])["domain"]["id"] == str(domain.id)

    @pytest.mark.parametrize(
        "client",
        [
            None,
            make_client(is_active=False),
            make_client(webhook_url=None),
            make_client(webhook_secret=None),
        ],
    )
    def test_nothing_is_sent_without_an_active_configured_client(self, client):
        result, post = run(make_domain(), client)
        assert result == "skipped"
        post.assert_not_called()

    def test_unknown_domain_is_skipped(self):
        post = MagicMock()
        with (
            patch("custom_domain.tasks.webhooks.get_sync_db") as get_db,
            patch("custom_domain.tasks.webhooks.httpx.post", post),
        ):
            session = MagicMock()
            session.execute.return_value.scalar_one_or_none.return_value = None
            get_db.return_value.__enter__ = MagicMock(return_value=session)
            get_db.return_value.__exit__ = MagicMock(return_value=False)
            assert deliver_webhook(str(uuid4()), "e", {}, "i", "t") == "skipped"
        post.assert_not_called()

    def test_a_non_2xx_answer_is_retried_with_back_off(self, monkeypatch):
        monkeypatch.setattr(settings, "webhook_retry_delay_seconds", 7)
        post = MagicMock(return_value=httpx.Response(503))
        with (
            patch.object(deliver_webhook, "retry", side_effect=Retry()) as retry,
            pytest.raises(Retry),
        ):
            run(make_domain(), make_client(), retries=2, post=post)
        retry.assert_called_once_with(countdown=28)

    def test_a_network_error_is_retried(self):
        post = MagicMock(side_effect=httpx.ConnectError("refused"))
        with (
            patch.object(deliver_webhook, "retry", side_effect=Retry()) as retry,
            pytest.raises(Retry),
        ):
            run(make_domain(), make_client(), post=post)
        retry.assert_called_once()

    def test_giving_up_after_the_last_retry(self):
        post = MagicMock(return_value=httpx.Response(500))
        result, _ = run(
            make_domain(), make_client(), retries=deliver_webhook.max_retries, post=post
        )
        assert result == "failed"

    def test_retry_limits_come_from_the_settings(self):
        assert deliver_webhook.max_retries == settings.webhook_max_retries
        assert deliver_webhook.default_retry_delay == settings.webhook_retry_delay_seconds

    def test_the_task_is_routed_to_the_worker_queue(self):
        from custom_domain.celery import celery_app

        route = celery_app.amqp.router.route({}, deliver_webhook.name)
        assert route["queue"].name == settings.celery_queue


class TestEventMapping:
    """Which progress events become webhooks."""

    @pytest.mark.parametrize(
        ("event_type", "payload", "name"),
        [
            ("status_change", {"status": "ssl_provisioning"}, "domain.status_changed"),
            ("completed", {"status": "active"}, "domain.active"),
            ("completed", {"status": "deprovisioning", "deleted": True}, "domain.deleted"),
            ("error", {"code": "X"}, "domain.failed"),
            ("step_started", {"step": "certbot"}, None),
            ("step_completed", {}, None),
            ("step_failed", {}, None),
            ("heartbeat", {}, None),
        ],
    )
    def test_names(self, event_type, payload, name):
        assert webhook_event_name(event_type, payload) == name

    def test_documented_events_are_the_ones_produced(self):
        from custom_domain.client.webhooks import EVENTS

        produced = {
            webhook_event_name(t, p)
            for t, p in [
                ("status_change", {}),
                ("completed", {}),
                ("completed", {"deleted": True}),
                ("error", {}),
            ]
        }
        assert produced == set(EVENTS)


class TestDispatch:
    """publish_event queues the delivery."""

    def test_a_status_change_is_queued(self, webhook_queue):
        with patch("custom_domain.services.events.redis"):
            publish_event("dom-1", "status_change", {"status": "active", "previous_status": "x"})

        webhook_queue.assert_called_once()
        kwargs = webhook_queue.call_args.kwargs
        domain_id, name, payload, delivery_id, created_at = kwargs["args"]
        assert (domain_id, name) == ("dom-1", "domain.status_changed")
        assert payload["status"] == "active"
        assert len(delivery_id) == 36
        assert created_at
        assert kwargs["retry"] is False

    def test_each_delivery_has_its_own_id(self, webhook_queue):
        notify_webhook("d", "completed", {})
        notify_webhook("d", "completed", {})
        ids = {c.kwargs["args"][3] for c in webhook_queue.call_args_list}
        assert len(ids) == 2

    def test_steps_are_not_queued(self, webhook_queue):
        with patch("custom_domain.services.events.redis"):
            publish_event("dom-1", "step_started", {"step": "certbot"})
        webhook_queue.assert_not_called()

    def test_an_unreachable_broker_does_not_break_the_event(self, webhook_queue):
        webhook_queue.side_effect = ConnectionError("broker down")
        notify_webhook("d", "error", {"code": "X"})  # must not raise

    def test_redis_failure_still_queues_the_webhook(self, webhook_queue):
        with patch("custom_domain.services.events.redis") as mock_redis:
            mock_redis.from_url.side_effect = ConnectionError("down")
            publish_event("dom-1", "error", {"code": "X"})
        webhook_queue.assert_called_once()
