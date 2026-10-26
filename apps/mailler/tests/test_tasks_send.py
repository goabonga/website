# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for send tasks."""

import uuid
from unittest.mock import MagicMock, patch

from mailler.models.email import EmailStatus
from mailler.tasks.send import (
    _update_provider_stats,
    send_email_task,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_db_ctx(session):
    """Create a mock context manager that yields *session*."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestUpdateProviderStats:
    def test_creates_new_stats_on_sent(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        _update_provider_stats(db, "brevo", "sent")

        db.add.assert_called_once()
        new_stats = db.add.call_args[0][0]
        assert new_stats.sent_count == 1
        db.commit.assert_called_once()

    def test_increments_existing_delivered(self):
        db = MagicMock()
        existing = MagicMock()
        existing.delivered_count = 5
        db.execute.return_value.scalar_one_or_none.return_value = existing

        _update_provider_stats(db, "brevo", "delivered")

        assert existing.delivered_count == 6
        db.commit.assert_called_once()

    def test_increments_bounced(self):
        db = MagicMock()
        existing = MagicMock()
        existing.bounced_count = 2
        db.execute.return_value.scalar_one_or_none.return_value = existing

        _update_provider_stats(db, "brevo", "bounced")

        assert existing.bounced_count == 3

    def test_increments_failed(self):
        db = MagicMock()
        existing = MagicMock()
        existing.failed_count = 0
        db.execute.return_value.scalar_one_or_none.return_value = existing

        _update_provider_stats(db, "brevo", "failed")

        assert existing.failed_count == 1

    def test_handles_none_count_on_new_record(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        _update_provider_stats(db, "ses", "bounced")

        new_stats = db.add.call_args[0][0]
        assert new_stats.bounced_count == 1

    def test_creates_new_stats_on_failed(self):
        """Cover lines 66->69: new ProviderStats record for 'failed' status."""
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        _update_provider_stats(db, "ses", "failed")

        db.add.assert_called_once()
        new_stats = db.add.call_args[0][0]
        assert new_stats.failed_count == 1
        db.commit.assert_called_once()


class TestSendEmailTask:
    def _setup_db(self, email_obj):
        """Return (mock_session, mock_get_sync_db_ctx)."""
        session = MagicMock()
        session.get.return_value = email_obj
        session.execute.return_value.scalar_one_or_none.return_value = None
        return session, _make_sync_db_ctx(session)

    def test_email_not_found(self):
        session = MagicMock()
        session.get.return_value = None
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_email_task(str(uuid.uuid4()))

        assert result == {"error": "Email not found"}

    def test_already_processed(self):
        email = MagicMock()
        email.status = EmailStatus.SENT.value
        session, ctx = self._setup_db(email)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_email_task(str(uuid.uuid4()))

        assert result == {"status": EmailStatus.SENT.value}

    def test_send_success(self):
        email_id = str(uuid.uuid4())
        email = MagicMock()
        email.id = email_id
        email.status = EmailStatus.PENDING.value
        email.provider = "brevo"
        email.metadata_ = None

        provider_result = MagicMock()
        provider_result.success = True
        provider_result.provider_message_id = "msg-456"

        mock_provider = MagicMock()
        mock_provider.send_email.return_value = provider_result

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.get_provider", return_value=mock_provider),
            patch("mailler.tasks.send._update_provider_stats"),
        ):
            result = send_email_task(email_id)

        assert result["status"] == EmailStatus.SENT.value
        assert result["message_id"] == "msg-456"

    def test_send_failure_max_retries(self):
        email_id = str(uuid.uuid4())
        email = MagicMock()
        email.id = email_id
        email.status = EmailStatus.PENDING.value
        email.provider = "brevo"
        email.retry_count = 2
        email.metadata_ = None

        provider_result = MagicMock()
        provider_result.success = False
        provider_result.error_message = "SMTP error"

        mock_provider = MagicMock()
        mock_provider.send_email.return_value = provider_result

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.get_provider", return_value=mock_provider),
            patch("mailler.tasks.send._update_provider_stats"),
        ):
            result = send_email_task(email_id)

        assert result["status"] == EmailStatus.FAILED.value
        assert result["error"] == "SMTP error"

    def test_max_retries_come_from_the_settings(self):
        email = MagicMock()
        email.status = EmailStatus.PENDING.value
        email.provider = "brevo"
        email.retry_count = 0
        email.metadata_ = None

        provider_result = MagicMock()
        provider_result.success = False
        provider_result.error_message = "SMTP error"
        mock_provider = MagicMock()
        mock_provider.send_email.return_value = provider_result

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.get_provider", return_value=mock_provider),
            patch("mailler.tasks.send._update_provider_stats"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.send_max_retries = 1
            result = send_email_task(str(uuid.uuid4()))

        assert result["status"] == EmailStatus.FAILED.value

    def test_send_failure_retry(self):
        email_id = str(uuid.uuid4())
        email = MagicMock()
        email.id = email_id
        email.status = EmailStatus.PENDING.value
        email.provider = "brevo"
        email.retry_count = 0
        email.metadata_ = None

        provider_result = MagicMock()
        provider_result.success = False
        provider_result.error_message = "Temporary error"

        mock_provider = MagicMock()
        mock_provider.send_email.return_value = provider_result

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.get_provider", return_value=mock_provider),
        ):
            try:
                send_email_task(email_id)
                raise AssertionError("Expected Exception")
            except Exception as e:
                assert str(e) == "Temporary error"

    def test_value_error_provider_not_configured(self):
        email_id = str(uuid.uuid4())
        email = MagicMock()
        email.id = email_id
        email.status = EmailStatus.PENDING.value
        email.provider = "unknown"
        email.metadata_ = None

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch(
                "mailler.tasks.send.get_provider",
                side_effect=ValueError("Provider unknown not configured"),
            ),
            patch("mailler.tasks.send._update_provider_stats"),
        ):
            result = send_email_task(email_id)

        assert result["status"] == EmailStatus.FAILED.value
        assert "not configured" in result["error"]

    def test_send_failure_below_max_retries(self):
        """Cover line 387: provider returns error but retry_count < max (1 < 3).

        This is the branch at line 227 where retry_count < 3 after increment,
        leading to db.commit() at line 249 and the raise at line 260.
        """
        email_id = str(uuid.uuid4())
        email = MagicMock()
        email.id = email_id
        email.status = EmailStatus.PENDING.value
        email.provider = "brevo"
        email.retry_count = 1  # After increment becomes 2, still < 3
        email.metadata_ = None

        provider_result = MagicMock()
        provider_result.success = False
        provider_result.error_message = "Rate limited"

        mock_provider = MagicMock()
        mock_provider.send_email.return_value = provider_result

        session, ctx = self._setup_db(email)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.get_provider", return_value=mock_provider),
        ):
            try:
                send_email_task(email_id)
                raise AssertionError("Expected Exception")
            except Exception as e:
                assert str(e) == "Rate limited"

        # Verify retry_count was incremented
        assert email.retry_count == 2
        assert email.error_message == "Rate limited"
        session.commit.assert_called()


class TestUnrecognisedStatusBranches:
    """Cover the elif-false branches when status doesn't match any case."""

    def test_update_provider_stats_unknown_status(self):
        """_update_provider_stats with unknown status skips all branches."""
        db = MagicMock()
        stats = MagicMock(sent_count=0, delivered_count=0, bounced_count=0, failed_count=0)
        db.execute.return_value.scalar_one_or_none.return_value = stats
        _update_provider_stats(db, "brevo", "queued")
        # No counter should be incremented
        assert stats.sent_count == 0
        assert stats.delivered_count == 0
        assert stats.bounced_count == 0
        assert stats.failed_count == 0
