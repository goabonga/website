# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the status callback service."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from mailler.services import callbacks
from mailler.services.callbacks import build_payload, notify_status_change, sign


def _email(**fields):
    email = MagicMock()
    email.id = uuid4()
    email.client_id = "app-one"
    email.status = "sent"
    email.to_email = "user@example.com"
    email.provider = "brevo"
    email.provider_message_id = "m-1"
    email.error_message = None
    email.metadata_ = {"workspace": 7}
    for key, value in fields.items():
        setattr(email, key, value)
    return email


class TestSign:
    def test_signature_covers_the_timestamp_and_the_body(self):
        expected = hmac.new(b"secret", b"1700000000.{}", hashlib.sha256).hexdigest()
        assert sign("secret", "1700000000", b"{}") == f"sha256={expected}"

    def test_signature_depends_on_the_secret_the_timestamp_and_the_body(self):
        reference = sign("secret", "1", b"body")
        assert sign("other", "1", b"body") != reference
        assert sign("secret", "2", b"body") != reference
        assert sign("secret", "1", b"other") != reference


class TestBuildPayload:
    def test_fields(self):
        email = _email(error_message="boom")
        moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        payload = json.loads(build_payload(email, "failed", moment))
        assert payload == {
            "event": "email.status",
            "email_id": str(email.id),
            "client_id": "app-one",
            "status": "failed",
            "to_email": "user@example.com",
            "provider": "brevo",
            "provider_message_id": "m-1",
            "error_message": "boom",
            "metadata": {"workspace": 7},
            "occurred_at": "2026-01-02T03:04:05+00:00",
        }

    def test_payload_is_deterministic_and_compact(self):
        email = _email()
        moment = datetime(2026, 1, 2, tzinfo=UTC)
        body = build_payload(email, "sent", moment)
        assert body == build_payload(email, "sent", moment)
        assert b": " not in body and b", " not in body

    def test_empty_metadata(self):
        assert json.loads(build_payload(_email(metadata_=None), "sent"))["metadata"] == {}


def _db(client):
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = client
    return db


class TestNotifyStatusChange:
    @pytest.fixture(autouse=True)
    def queue(self):
        with patch("mailler.tasks.callbacks.deliver_status_callback") as task:
            yield task

    def test_a_client_with_a_callback_is_notified(self, queue):
        email = _email(status="delivered")
        assert notify_status_change(_db(MagicMock(callback_url="https://app.example/hook")), email)
        queue.delay.assert_called_once_with(str(email.id), "delivered")

    @pytest.mark.parametrize("status", ["sent", "delivered", "bounced", "failed"])
    def test_final_statuses_are_notified(self, status, queue):
        client = MagicMock(callback_url="https://app.example/hook")
        assert notify_status_change(_db(client), _email(status=status))

    @pytest.mark.parametrize("status", ["pending", "queued"])
    def test_internal_statuses_are_not(self, status, queue):
        db = _db(MagicMock(callback_url="https://app.example/hook"))
        assert notify_status_change(db, _email(status=status)) is False
        db.execute.assert_not_called()

    def test_client_without_a_callback(self, queue):
        assert notify_status_change(_db(MagicMock(callback_url=None)), _email()) is False
        queue.delay.assert_not_called()

    def test_unregistered_client(self, queue):
        assert notify_status_change(_db(None), _email()) is False

    def test_email_without_a_client(self, queue):
        db = _db(None)
        assert notify_status_change(db, _email(client_id=None)) is False
        db.execute.assert_not_called()

    def test_the_registry_is_queried_for_the_client_of_the_email(self, queue):
        db = _db(None)
        notify_status_change(db, _email(client_id="app-two"))
        assert db.execute.call_args.args[0].compile().params["client_id_1"] == "app-two"

    def test_a_broker_failure_never_propagates(self, queue):
        queue.delay.side_effect = ConnectionError("broker down")
        db = _db(MagicMock(callback_url="https://app.example/hook"))
        assert notify_status_change(db, _email()) is False

    def test_a_database_failure_never_propagates(self, queue):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("database down")
        assert notify_status_change(db, _email()) is False


def test_notified_statuses_are_the_final_ones():
    assert set(callbacks.NOTIFIED_STATUSES) == {"sent", "delivered", "bounced", "failed"}
