# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for scheduler tasks."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from mailler.models.campaign import CampaignStatus
from mailler.models.email import EmailStatus
from mailler.tasks.scheduler import (
    aggregate_daily_stats,
    check_scheduled_campaigns,
    cleanup_old_emails,
    process_scheduled_emails,
    requeue_stuck_emails,
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


def _make_email(email_id=None, status=EmailStatus.PENDING.value):
    email = MagicMock()
    email.id = email_id or uuid.uuid4()
    email.status = status
    email.created_at = datetime.now(UTC) - timedelta(minutes=10)
    email.scheduled_at = None
    return email


# ---------------------------------------------------------------------------
# requeue_stuck_emails
# ---------------------------------------------------------------------------


class TestRequeueStuckEmails:
    def test_no_stuck_emails(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = requeue_stuck_emails()

        assert result == {"requeued": 0}

    def test_requeues_stuck(self):
        email = _make_email()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [email]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.send_email_task") as mock_task,
        ):
            result = requeue_stuck_emails()

        mock_task.delay.assert_called_once_with(str(email.id))
        assert result == {"requeued": 1}

    def test_handles_requeue_exception(self):
        email = _make_email()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [email]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch(
                "mailler.tasks.scheduler.send_email_task",
            ) as mock_task,
        ):
            mock_task.delay.side_effect = Exception("broker down")
            result = requeue_stuck_emails()

        assert result == {"requeued": 0}


# ---------------------------------------------------------------------------
# process_scheduled_emails
# ---------------------------------------------------------------------------


class TestProcessScheduledEmails:
    def test_no_scheduled(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = process_scheduled_emails()

        assert result == {"queued": 0}

    def test_queues_due_emails(self):
        email = _make_email()
        email.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [email]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.send_email_task") as mock_task,
        ):
            result = process_scheduled_emails()

        mock_task.delay.assert_called_once()
        assert result == {"queued": 1}

    def test_handles_queue_exception(self):
        email = _make_email()
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = [email]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.send_email_task") as mock_task,
        ):
            mock_task.delay.side_effect = Exception("broker down")
            result = process_scheduled_emails()

        assert result == {"queued": 0}


class TestSchedulerSettings:
    """The thresholds and batch sizes come from the settings."""

    def test_stuck_threshold_and_batch_come_from_the_settings(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.settings") as mock_settings,
        ):
            mock_settings.stuck_email_minutes = 7
            mock_settings.stuck_email_batch = 11
            requeue_stuck_emails()

        statement = session.execute.call_args.args[0]
        assert statement._limit == 11
        cutoff = statement.compile().params["created_at_1"].replace(tzinfo=UTC)
        assert abs(datetime.now(UTC) - cutoff - timedelta(minutes=7)) < timedelta(seconds=30)

    def test_scheduled_batch_comes_from_the_settings(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.settings") as mock_settings,
        ):
            mock_settings.scheduled_email_batch = 13
            process_scheduled_emails()

        assert session.execute.call_args.args[0]._limit == 13

    def test_retention_comes_from_the_settings(self):
        session = MagicMock()
        session.execute.return_value.rowcount = 0
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.settings") as mock_settings,
        ):
            mock_settings.email_retention_days = 5
            cleanup_old_emails()

        cutoff = session.execute.call_args.args[0].compile().params["created_at_1"]
        assert abs(datetime.now(UTC) - cutoff.replace(tzinfo=UTC) - timedelta(days=5)) < timedelta(
            seconds=30
        )


# ---------------------------------------------------------------------------
# cleanup_old_emails
# ---------------------------------------------------------------------------


class TestCleanupOldEmails:
    def test_deletes_old(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 42
        session.execute.return_value = mock_result
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = cleanup_old_emails(days=30)

        assert result == {"deleted": 42}
        session.commit.assert_called_once()

    def test_nothing_to_delete(self):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute.return_value = mock_result
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = cleanup_old_emails()

        assert result == {"deleted": 0}


# ---------------------------------------------------------------------------
# aggregate_daily_stats
# ---------------------------------------------------------------------------


class TestAggregateDailyStats:
    def test_no_emails_yesterday(self):
        session = MagicMock()
        session.execute.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = aggregate_daily_stats()

        assert result["stats"] == {}
        session.commit.assert_called_once()

    def test_aggregates_by_provider(self):
        session = MagicMock()
        # First call: aggregate query results
        rows = [
            ("brevo", EmailStatus.SENT.value, 10),
            ("brevo", EmailStatus.DELIVERED.value, 8),
            ("brevo", EmailStatus.BOUNCED.value, 1),
            ("brevo", EmailStatus.FAILED.value, 1),
        ]

        agg_result = MagicMock()
        agg_result.all.return_value = rows

        # Second call: stats lookup returns None (create new)
        stats_result = MagicMock()
        stats_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [agg_result, stats_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = aggregate_daily_stats()

        assert result["stats"]["brevo"]["sent"] == 10
        assert result["stats"]["brevo"]["delivered"] == 8
        assert result["stats"]["brevo"]["bounced"] == 1
        assert result["stats"]["brevo"]["failed"] == 1
        session.add.assert_called_once()

    def test_updates_existing_stats(self):
        session = MagicMock()
        rows = [("ses", EmailStatus.SENT.value, 5)]

        agg_result = MagicMock()
        agg_result.all.return_value = rows

        existing_stats = MagicMock()
        stats_result = MagicMock()
        stats_result.scalar_one_or_none.return_value = existing_stats

        session.execute.side_effect = [agg_result, stats_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            aggregate_daily_stats()

        assert existing_stats.sent_count == 5
        session.add.assert_not_called()  # Did not add new record


# ---------------------------------------------------------------------------
# check_scheduled_campaigns
# ---------------------------------------------------------------------------


class TestCheckScheduledCampaigns:
    def test_no_due_campaigns(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = check_scheduled_campaigns()

        assert result == {"started": 0}

    def test_starts_campaign(self):
        campaign = MagicMock()
        campaign.id = 1
        campaign.group_id = 10
        campaign.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)

        session = MagicMock()

        # First execute: campaigns query
        campaigns_result = MagicMock()
        campaigns_result.scalars.return_value.all.return_value = [campaign]

        # Second execute: count active contacts
        count_result = MagicMock()
        count_result.scalar.return_value = 50

        session.execute.side_effect = [campaigns_result, count_result]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.send_campaign_task") as mock_task,
        ):
            mock_task.delay.return_value = MagicMock(id="task-abc")
            result = check_scheduled_campaigns()

        assert result == {"started": 1}
        assert campaign.status == CampaignStatus.SENDING.value
        assert campaign.total_recipients == 50
        assert campaign.task_id == "task-abc"
        mock_task.delay.assert_called_once_with(1)

    def test_skips_campaign_no_active_contacts(self):
        campaign = MagicMock()
        campaign.id = 2
        campaign.group_id = 20

        session = MagicMock()

        campaigns_result = MagicMock()
        campaigns_result.scalars.return_value.all.return_value = [campaign]

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        session.execute.side_effect = [campaigns_result, count_result]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx),
            patch("mailler.tasks.scheduler.send_campaign_task") as mock_task,
        ):
            result = check_scheduled_campaigns()

        assert result == {"started": 0}
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Branch coverage: aggregate_daily_stats with unknown email status
# ---------------------------------------------------------------------------


class TestAggregateDailyStatsUnknownStatus:
    """Cover the elif-false branch when a status doesn't match any case."""

    def test_unknown_status_skipped(self):
        """Emails with unrecognised status (e.g. 'queued') are ignored."""
        session = MagicMock()
        ctx = _make_sync_db_ctx(session)

        # First execute: rows grouped by provider/status
        rows_result = MagicMock()
        rows_result.all.return_value = [("brevo", "queued", 5)]

        # Second execute: upsert lookup returns None (create new)
        upsert_result = MagicMock()
        upsert_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [rows_result, upsert_result]

        with patch("mailler.tasks.scheduler.get_sync_db", return_value=ctx):
            result = aggregate_daily_stats()

        # Provider appears in stats with all counters at zero
        assert "brevo" in result["stats"]
        assert result["stats"]["brevo"] == {"sent": 0, "delivered": 0, "bounced": 0, "failed": 0}
