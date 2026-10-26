# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the delivery of the status callbacks."""

import json
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import httpx
import pytest
from mailler.services.callbacks import sign
from mailler.tasks.callbacks import CallbackFailed, deliver_status_callback


def _email(**fields):
    email = MagicMock()
    email.id = uuid.uuid4()
    email.client_id = "app-one"
    email.status = "sent"
    email.to_email = "user@example.com"
    email.provider = "brevo"
    email.provider_message_id = "m-1"
    email.error_message = None
    email.metadata_ = {}
    for key, value in fields.items():
        setattr(email, key, value)
    return email


def _client(**fields):
    values = {"callback_url": "https://app.example/hook", "callback_secret": "s" * 20}
    values.update(fields)
    return MagicMock(**values)


@contextmanager
def _database(email, client):
    session = MagicMock()
    session.get.return_value = email
    session.execute.return_value.scalar_one_or_none.return_value = client

    @contextmanager
    def get_sync_db():
        yield session

    with patch("mailler.tasks.callbacks.get_sync_db", get_sync_db):
        yield session


def _run(email, client, post):
    with _database(email, client), patch("mailler.tasks.callbacks.httpx.post", post):
        return deliver_status_callback(str(email.id), email.status)


class TestDelivery:
    def test_the_notification_is_posted_signed(self):
        email = _email()
        post = MagicMock(return_value=httpx.Response(200))

        result = _run(email, _client(), post)

        assert result == {"delivered": True, "http_status": 200}
        url = post.call_args.args[0]
        headers = post.call_args.kwargs["headers"]
        body = post.call_args.kwargs["content"]
        assert url == "https://app.example/hook"
        assert json.loads(body)["email_id"] == str(email.id)
        assert json.loads(body)["status"] == "sent"
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Mailler-Event"] == "email.status"
        assert headers["X-Mailler-Signature"] == sign(
            "s" * 20, headers["X-Mailler-Timestamp"], body
        )

    def test_the_timeout_comes_from_the_settings(self):
        post = MagicMock(return_value=httpx.Response(204))
        with patch("mailler.tasks.callbacks.settings") as mock_settings:
            mock_settings.callback_timeout = 3
            _run(_email(), _client(), post)
        assert post.call_args.kwargs["timeout"] == 3

    @pytest.mark.parametrize("code", [400, 404, 500, 503])
    def test_a_refusal_is_retried(self, code):
        with pytest.raises(CallbackFailed, match=str(code)):
            _run(_email(), _client(), MagicMock(return_value=httpx.Response(code)))

    def test_a_network_error_is_retried(self):
        post = MagicMock(side_effect=httpx.ConnectError("unreachable"))
        with pytest.raises(CallbackFailed, match="unreachable"):
            _run(_email(), _client(), post)

    def test_unknown_email(self):
        post = MagicMock()
        with _database(None, _client()), patch("mailler.tasks.callbacks.httpx.post", post):
            assert deliver_status_callback(str(uuid.uuid4()), "sent") == {
                "skipped": "email not found"
            }
        post.assert_not_called()

    def test_email_without_a_client(self):
        post = MagicMock()
        result = _run(_email(client_id=None), _client(), post)
        assert result == {"skipped": "email not found"}
        post.assert_not_called()

    @pytest.mark.parametrize(
        "client",
        [
            None,
            _client(callback_url=None),
            _client(callback_secret=None),
        ],
    )
    def test_nothing_is_posted_without_a_complete_callback(self, client):
        post = MagicMock()
        assert _run(_email(), client, post) == {"skipped": "no callback configured"}
        post.assert_not_called()

    def test_the_status_of_the_trigger_is_notified(self):
        email = _email(status="delivered")
        post = MagicMock(return_value=httpx.Response(200))
        with _database(email, _client()), patch("mailler.tasks.callbacks.httpx.post", post):
            deliver_status_callback(str(email.id), "sent")
        assert json.loads(post.call_args.kwargs["content"])["status"] == "sent"


class TestTaskConfiguration:
    def test_retries_come_from_the_settings(self):
        from mailler.config import settings

        assert deliver_status_callback.max_retries == settings.callback_max_retries
        assert deliver_status_callback.retry_backoff == settings.callback_retry_delay
        assert deliver_status_callback.autoretry_for == (CallbackFailed,)

    def test_the_task_is_registered(self):
        from mailler import tasks  # noqa: F401
        from mailler.celery import celery_app

        assert "mailler.tasks.callbacks.deliver_status_callback" in celery_app.tasks
