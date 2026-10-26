# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for webhook delivery tasks.

DB and HTTP are mocked; these focus on the state transitions of the
delivery row (success, retry scheduling, failure after max attempts).
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from auth.db.models.tenant import WebhookDeliveryStatus
from auth.tasks.webhooks import (
    _next_retry_delay,
    cleanup_webhook_deliveries,
    deliver_webhook,
    retry_pending_webhooks,
)


def _make_delivery(attempt=0, max_attempts=5, status=WebhookDeliveryStatus.PENDING):
    return SimpleNamespace(
        id=uuid.uuid4(),
        webhook_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        event="user.created",
        attempt=attempt,
        max_attempts=max_attempts,
        status=status,
        request_body={"event": "user.created", "data": {}},
        request_url="https://example.com/hook",
        request_headers={},
        response_status=None,
        response_headers=None,
        response_body=None,
        error=None,
        duration_ms=None,
        delivered_at=None,
        next_retry_at=None,
    )


def _make_webhook():
    return SimpleNamespace(
        id=uuid.uuid4(),
        url="https://example.com/hook",
        secret="secret",
        headers={},
        last_triggered_at=None,
        last_status_code=None,
        last_error=None,
        failure_count=0,
    )


def _mock_db(delivery, webhook):
    """Build a mock session where ``delivery.webhook_id`` resolves to ``webhook``."""
    delivery.webhook_id = webhook.id
    db = MagicMock()

    def _get(cls, pk):
        from auth.db.models.tenant import TenantWebhook, WebhookDelivery

        if cls is WebhookDelivery and str(pk) == str(delivery.id):
            return delivery
        if cls is TenantWebhook and str(pk) == str(webhook.id):
            return webhook
        return None

    db.get.side_effect = _get
    return db


def _patch_sync_db(db):
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestDeliverWebhook:
    @patch("auth.tasks.webhooks.validate_target_url")
    @patch("auth.tasks.webhooks.httpx.Client")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_success_marks_row_success(self, mock_db_cm, mock_client_cls, _validate):
        delivery = _make_delivery()
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        resp = MagicMock(status_code=200, headers={"Content-Type": "text/plain"}, text="ok")
        client_cm = MagicMock()
        client_cm.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=resp)))
        client_cm.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = client_cm

        result = deliver_webhook(str(delivery.id))

        assert result["status"] == "success"
        assert delivery.status == WebhookDeliveryStatus.SUCCESS
        assert delivery.response_status == 200
        assert delivery.attempt == 1
        assert webhook.failure_count == 0
        assert webhook.last_status_code == 200

    @patch("auth.tasks.webhooks.validate_target_url")
    @patch("auth.tasks.webhooks.httpx.Client")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_non_2xx_schedules_retry(self, mock_db_cm, mock_client_cls, _validate):
        delivery = _make_delivery(attempt=0, max_attempts=5)
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        resp = MagicMock(status_code=503, headers={}, text="down")
        client_cm = MagicMock()
        client_cm.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=resp)))
        client_cm.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = client_cm

        result = deliver_webhook(str(delivery.id))

        assert result["status"] == "retrying"
        assert delivery.status == WebhookDeliveryStatus.RETRYING
        assert delivery.next_retry_at is not None
        assert delivery.attempt == 1
        assert webhook.failure_count == 1

    @patch("auth.tasks.webhooks.validate_target_url")
    @patch("auth.tasks.webhooks.httpx.Client")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_non_2xx_final_attempt_marks_failed(self, mock_db_cm, mock_client_cls, _validate):
        delivery = _make_delivery(attempt=4, max_attempts=5)
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        resp = MagicMock(status_code=500, headers={}, text="")
        client_cm = MagicMock()
        client_cm.__enter__ = MagicMock(return_value=MagicMock(post=MagicMock(return_value=resp)))
        client_cm.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = client_cm

        result = deliver_webhook(str(delivery.id))

        assert result["status"] == "failed"
        assert delivery.status == WebhookDeliveryStatus.FAILED
        assert delivery.next_retry_at is None
        assert delivery.attempt == 5

    @patch("auth.tasks.webhooks.validate_target_url")
    @patch("auth.tasks.webhooks.httpx.Client")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_transport_error_captured(self, mock_db_cm, mock_client_cls, _validate):
        delivery = _make_delivery()
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        client_inst = MagicMock()
        client_inst.post.side_effect = httpx.ConnectTimeout("boom")
        client_cm = MagicMock()
        client_cm.__enter__ = MagicMock(return_value=client_inst)
        client_cm.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = client_cm

        result = deliver_webhook(str(delivery.id))

        assert result["status"] == "retrying"
        assert "ConnectTimeout" in delivery.error
        assert delivery.response_status is None

    @patch("auth.tasks.webhooks.get_sync_db")
    def test_missing_delivery_returns_not_found(self, mock_db_cm):
        db = MagicMock()
        db.get.return_value = None
        mock_db_cm.return_value = _patch_sync_db(db)

        result = deliver_webhook(str(uuid.uuid4()))
        assert result["status"] == "not_found"

    @patch("auth.tasks.webhooks.get_sync_db")
    def test_already_finalized_delivery_is_skipped(self, mock_db_cm):
        delivery = _make_delivery(status=WebhookDeliveryStatus.SUCCESS)
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        result = deliver_webhook(str(delivery.id))
        assert result["status"] == "skipped"

    @patch("auth.tasks.webhooks.validate_target_url", side_effect=Exception("bad url"))
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_invalid_url_marks_failed(self, mock_db_cm, _validate):
        from auth.services.webhook import WebhookURLError

        _validate.side_effect = WebhookURLError("unsafe")

        delivery = _make_delivery()
        webhook = _make_webhook()
        mock_db_cm.return_value = _patch_sync_db(_mock_db(delivery, webhook))

        result = deliver_webhook(str(delivery.id))
        assert result["status"] == "failed"
        assert delivery.status == WebhookDeliveryStatus.FAILED
        assert "unsafe" in (delivery.error or "")


class TestBackoff:
    def test_monotonically_non_decreasing(self):
        prev = 0
        for attempt in range(1, 10):
            delay = _next_retry_delay(attempt)
            assert delay >= prev
            prev = delay

    def test_first_retry_is_minute(self):
        assert _next_retry_delay(1) == 60


class TestRetryPendingWebhooks:
    @patch("auth.tasks.webhooks.deliver_webhook")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_reenqueues_due_deliveries(self, mock_db_cm, mock_deliver):
        db = MagicMock()
        ids = [uuid.uuid4(), uuid.uuid4()]
        result = MagicMock()
        result.all.return_value = [(i,) for i in ids]
        db.execute.return_value = result
        mock_db_cm.return_value = _patch_sync_db(db)

        out = retry_pending_webhooks()

        assert out == {"rescheduled": 2}
        assert mock_deliver.delay.call_count == 2

    @patch("auth.tasks.webhooks.deliver_webhook")
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_no_due_deliveries(self, mock_db_cm, mock_deliver):
        db = MagicMock()
        result = MagicMock()
        result.all.return_value = []
        db.execute.return_value = result
        mock_db_cm.return_value = _patch_sync_db(db)

        assert retry_pending_webhooks() == {"rescheduled": 0}
        mock_deliver.delay.assert_not_called()


class TestCleanup:
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_counts_age_and_cap_deletions(self, mock_db_cm):
        db = MagicMock()

        age_result = MagicMock()
        age_result.rowcount = 7
        hooks_result = MagicMock()
        hooks_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [age_result, hooks_result]
        mock_db_cm.return_value = _patch_sync_db(db)

        out = cleanup_webhook_deliveries()

        assert out == {"deleted_by_age": 7, "deleted_by_cap": 0}


# Silence unused-import warnings in lint for datetime/UTC used in fixtures.
_ = (datetime, UTC)


class TestTruncateBody:
    def test_short_body_returned_unchanged(self):
        from auth.tasks.webhooks import _truncate_body

        assert _truncate_body("ok") == "ok"

    def test_oversized_body_is_truncated(self):
        from auth.tasks.webhooks import _truncate_body

        with patch("auth.tasks.webhooks.settings") as mock_settings:
            mock_settings.webhook_response_body_max_bytes = 8
            result = _truncate_body("0123456789abcdef")

        assert result == "01234567... [truncated]"


class TestDeliverWebhookMissingConfiguration:
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_deleted_webhook_marks_delivery_failed(self, mock_db_cm):
        delivery = _make_delivery()
        db = MagicMock()
        db.get.side_effect = lambda cls, pk: delivery if cls.__name__ == "WebhookDelivery" else None
        mock_db_cm.return_value = _patch_sync_db(db)

        out = deliver_webhook(str(delivery.id))

        assert out == {
            "status": "failed",
            "delivery_id": str(delivery.id),
            "reason": "missing_webhook",
        }
        assert delivery.status == WebhookDeliveryStatus.FAILED
        assert delivery.error == "Webhook configuration was deleted"
        assert delivery.delivered_at is not None


class TestCleanupPerHookCap:
    @patch("auth.tasks.webhooks.get_sync_db")
    def test_overflow_rows_are_counted(self, mock_db_cm):
        db = MagicMock()

        age_result = MagicMock()
        age_result.rowcount = 0
        hook_ids = [uuid.uuid4(), uuid.uuid4()]
        hooks_result = MagicMock()
        hooks_result.scalars.return_value.all.return_value = hook_ids

        # Per hook: a SELECT for the overflow ids, then a DELETE.
        overflow_a = MagicMock()
        overflow_a.scalars.return_value.all.return_value = [uuid.uuid4()]
        delete_a = MagicMock()
        delete_a.rowcount = 1
        overflow_b = MagicMock()
        overflow_b.scalars.return_value.all.return_value = []

        db.execute.side_effect = [age_result, hooks_result, overflow_a, delete_a, overflow_b]
        mock_db_cm.return_value = _patch_sync_db(db)

        assert cleanup_webhook_deliveries() == {"deleted_by_age": 0, "deleted_by_cap": 1}

    @patch("auth.tasks.webhooks.get_sync_db")
    def test_nothing_deleted_skips_summary_log(self, mock_db_cm):
        db = MagicMock()

        age_result = MagicMock()
        age_result.rowcount = 0
        hooks_result = MagicMock()
        hooks_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [age_result, hooks_result]
        mock_db_cm.return_value = _patch_sync_db(db)

        assert cleanup_webhook_deliveries() == {"deleted_by_age": 0, "deleted_by_cap": 0}
