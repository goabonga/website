# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for send tasks."""

import uuid
from unittest.mock import MagicMock, patch

from mailler.models.campaign import CampaignStatus, EmailSendStatus
from mailler.models.email import EmailStatus
from mailler.tasks.send import (
    _convert_percent_syntax,
    _update_email_send_status,
    _update_provider_stats,
    send_campaign_task,
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


# ---------------------------------------------------------------------------
# _convert_percent_syntax
# ---------------------------------------------------------------------------


class TestConvertPercentSyntax:
    def test_simple(self):
        assert _convert_percent_syntax("Hello %name%") == "Hello {{ name }}"

    def test_multiple(self):
        result = _convert_percent_syntax("%first% %last%")
        assert result == "{{ first }} {{ last }}"

    def test_no_match(self):
        assert _convert_percent_syntax("Hello world") == "Hello world"

    def test_escaped_double_percent(self):
        assert _convert_percent_syntax("%%escaped%%") == "%%escaped%%"

    def test_underscore_var(self):
        assert _convert_percent_syntax("%first_name%") == "{{ first_name }}"


# ---------------------------------------------------------------------------
# _update_provider_stats
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _update_email_send_status
# ---------------------------------------------------------------------------


class TestUpdateEmailSendStatus:
    def test_no_metadata(self):
        db = MagicMock()
        email = MagicMock()
        email.metadata_ = None

        _update_email_send_status(db, email, "sent")
        db.get.assert_not_called()

    def test_no_email_send_id(self):
        db = MagicMock()
        email = MagicMock()
        email.metadata_ = {"campaign_id": "1"}

        _update_email_send_status(db, email, "sent")
        db.get.assert_not_called()

    def test_sent_updates_email_send_and_campaign(self):
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            "campaign_id": "1",
        }

        email_send = MagicMock()
        campaign = MagicMock()
        campaign.sent_count = 10

        db.get.side_effect = [email_send, campaign]

        _update_email_send_status(db, email, "sent", message_id="msg-123")

        assert email_send.status == EmailSendStatus.SENT.value
        assert email_send.message_id == "msg-123"
        assert campaign.sent_count == 11

    def test_failed_updates_email_send_and_campaign(self):
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            "campaign_id": "2",
        }

        email_send = MagicMock()
        campaign = MagicMock()
        campaign.failed_count = 0

        db.get.side_effect = [email_send, campaign]

        _update_email_send_status(db, email, "failed", error_message="timeout")

        assert email_send.status == EmailSendStatus.FAILED.value
        assert email_send.error_message == "timeout"
        assert campaign.failed_count == 1

    def test_email_send_not_found(self):
        db = MagicMock()
        email = MagicMock()
        email.metadata_ = {"email_send_id": str(uuid.uuid4())}

        db.get.return_value = None

        # Should not raise
        _update_email_send_status(db, email, "sent")

    def test_exception_logged(self):
        db = MagicMock()
        email = MagicMock()
        email.metadata_ = {"email_send_id": str(uuid.uuid4())}
        db.get.side_effect = Exception("DB error")

        # Should not raise
        _update_email_send_status(db, email, "sent")

    def test_email_send_found_no_campaign_id(self):
        """Cover lines 112->exit: email_send found but no campaign_id in metadata."""
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            # No campaign_id
        }

        email_send = MagicMock()
        db.get.return_value = email_send

        _update_email_send_status(db, email, "sent", message_id="msg-abc")

        assert email_send.status == EmailSendStatus.SENT.value
        assert email_send.message_id == "msg-abc"
        # db.get called once for email_send, not for campaign
        db.get.assert_called_once()
        # commit called once (for email_send update only)
        db.commit.assert_called_once()

    def test_campaign_not_found(self):
        """Cover lines 114->exit: email_send found, campaign_id present, but campaign is None."""
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            "campaign_id": "999",
        }

        email_send = MagicMock()
        # First db.get returns email_send, second returns None (campaign not found)
        db.get.side_effect = [email_send, None]

        _update_email_send_status(db, email, "sent", message_id="msg-xyz")

        assert email_send.status == EmailSendStatus.SENT.value
        assert email_send.message_id == "msg-xyz"
        # commit called once for email_send, but campaign stats not updated
        assert db.get.call_count == 2
        db.commit.assert_called_once()

    def test_failed_no_campaign_id(self):
        """Cover lines 106->109 and 112->exit for 'failed' status without campaign_id."""
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            # No campaign_id
        }

        email_send = MagicMock()
        db.get.return_value = email_send

        _update_email_send_status(db, email, "failed", error_message="provider down")

        assert email_send.status == EmailSendStatus.FAILED.value
        assert email_send.error_message == "provider down"
        db.get.assert_called_once()
        db.commit.assert_called_once()

    def test_failed_campaign_not_found(self):
        """Cover lines 106->109 and 114->exit: failed status, campaign_id but campaign not found."""
        db = MagicMock()
        email_send_id = str(uuid.uuid4())
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": email_send_id,
            "campaign_id": "42",
        }

        email_send = MagicMock()
        db.get.side_effect = [email_send, None]

        _update_email_send_status(db, email, "failed", error_message="timeout")

        assert email_send.status == EmailSendStatus.FAILED.value
        assert email_send.error_message == "timeout"
        assert db.get.call_count == 2
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# send_email_task
# ---------------------------------------------------------------------------


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
            patch("mailler.tasks.send._update_email_send_status"),
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
            patch("mailler.tasks.send._update_email_send_status"),
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
            patch("mailler.tasks.send._update_email_send_status"),
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


# ---------------------------------------------------------------------------
# send_campaign_task
# ---------------------------------------------------------------------------


class TestSendCampaignTask:
    def test_campaign_not_found(self):
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_campaign_task(999)

        assert result == {"error": "Campaign not found"}

    def test_wrong_status(self):
        campaign = MagicMock()
        campaign.status = CampaignStatus.DRAFT.value

        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = campaign
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_campaign_task(1)

        assert result["skipped"] is True

    def test_no_template(self):
        campaign = MagicMock()
        campaign.status = CampaignStatus.SENDING.value
        campaign.template = None

        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = campaign
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_campaign_task(1)

        assert result == {"error": "No template"}
        assert campaign.status == CampaignStatus.FAILED.value

    def test_no_group(self):
        campaign = MagicMock()
        campaign.status = CampaignStatus.SENDING.value
        campaign.template = MagicMock()
        campaign.group_id = None

        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = campaign
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.send.get_sync_db", return_value=ctx):
            result = send_campaign_task(1)

        assert result == {"error": "No group"}

    def test_success_with_contacts(self):
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 1

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = None
        campaign.template = template

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.full_name = "John Doe"
        contact.custom_fields = None

        session = MagicMock()

        # session.execute call sequence:
        # 1. Load campaign (scalar_one_or_none)
        # 2. Existing sends (fetchall)
        # 3. Contacts query (scalars().all())
        # 4. Sent count (scalar)
        # 5. Total queued (scalar)
        # flush/add/commit/refresh are separate session methods

        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign

        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []

        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 1

        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 1

        session.execute.side_effect = [
            campaign_result,  # load campaign
            existing_sends_result,  # existing sends
            contacts_result,  # contacts
            sent_count_result,  # sent count
            total_queued_result,  # total queued
        ]

        session.flush = MagicMock()
        session.refresh = MagicMock()
        session.commit = MagicMock()

        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task") as mock_send_task,
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50

            result = send_campaign_task(1)

        assert result["queued"] == 1
        assert result["failed"] == 0
        mock_send_task.delay.assert_called_once()

    def test_success_with_plain_text(self):
        """Cover line 387: plain_text template with %var% syntax."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 1

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = "Hello %first_name%"  # %var% syntax
        campaign.template = template

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.full_name = "John Doe"
        contact.custom_fields = {"company": "Acme"}  # Also covers line 429

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 1
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 1

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.refresh = MagicMock()
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result["queued"] == 1

    def test_contact_processing_exception(self):
        """Cover lines 482-492: exception during contact processing."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 1

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "{{ first_name }}"
        template.plain_text = None
        campaign.template = template

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.full_name = "John Doe"
        contact.custom_fields = None

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 0

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock(side_effect=Exception("DB flush error"))
        session.refresh = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result["failed"] == 1
        assert result["queued"] == 0
        session.rollback.assert_called()

    def test_campaign_subject_override(self):
        """Cover campaign with subject_override set."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = "Override Subject {{ first_name }}"
        campaign.from_email = None  # Test default_from fallback
        campaign.from_name = None  # Test default_from_name fallback
        campaign.reply_to = "reply@test.com"
        campaign.provider = None  # Test the platform provider fallback
        campaign.total_recipients = 1

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Original Subject"
        template.plain_text = None
        campaign.template = template

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.full_name = "John Doe"
        contact.custom_fields = None

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 1
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 1

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.refresh = MagicMock()
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = "fallback-provider"
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result["queued"] == 1
        emails = [c.args[0] for c in session.add.call_args_list if hasattr(c.args[0], "provider")]
        assert emails[0].provider == "fallback-provider"
        assert emails[0].from_email == "default@test.com"
        # the emails of a campaign belong to the client that owns it
        assert emails[0].client_id == "app-one"

    @staticmethod
    def _run_with_template(template, contact):
        """Run the campaign task for one contact and return (result, campaign, session)."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 1
        campaign.template = template

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            count_result,
            count_result,
        ]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
        ):
            result = send_campaign_task(1)
        return result, campaign, session

    @staticmethod
    def _contact(first_name):
        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = first_name
        contact.last_name = ""
        contact.full_name = first_name
        contact.custom_fields = None
        return contact

    def test_html_is_escaped_but_not_the_subject(self):
        template = MagicMock(
            html_compiled="<p>{{ first_name }}</p>",
            subject_template="Hi {{ first_name }}",
            plain_text="Hello %first_name%",
        )

        result, _, session = self._run_with_template(template, self._contact("<b>Tom & Jerry</b>"))

        assert result["queued"] == 1
        email = next(
            c.args[0] for c in session.add.call_args_list if hasattr(c.args[0], "html_content")
        )
        assert email.html_content == "<p>&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;</p>"
        assert email.subject == "Hi <b>Tom & Jerry</b>"
        assert email.text_content == "Hello <b>Tom & Jerry</b>"

    def test_hostile_template_does_not_run(self):
        template = MagicMock(
            html_compiled="<p>{{ ''.__class__.__mro__ }}</p>",
            subject_template="Hi",
            plain_text=None,
        )

        result, _, session = self._run_with_template(template, self._contact("Ann"))

        assert result["queued"] == 0
        assert result["failed"] == 1
        assert not any(hasattr(c.args[0], "html_content") for c in session.add.call_args_list)

    def test_template_that_does_not_compile_fails_the_campaign(self):
        template = MagicMock(
            html_compiled="<p>{% if %}</p>", subject_template="Hi", plain_text=None
        )

        result, campaign, _ = self._run_with_template(template, self._contact("Ann"))

        assert result == {"error": "Invalid template"}
        assert campaign.status == CampaignStatus.FAILED.value

    def test_campaign_without_sender_or_provider_fails(self):
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = None
        campaign.from_name = None
        campaign.provider = None
        campaign.template = MagicMock(
            html_compiled="<p>x</p>", subject_template="Subject", plain_text=None
        )

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        session.execute.return_value = campaign_result
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = ""
            mock_settings.default_from_name = ""
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result == {"error": "No sender or provider"}
        assert campaign.status == CampaignStatus.FAILED.value

    def test_campaign_pause_during_batch(self):
        """Cover lines 406-416: campaign pause handling during batch processing."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 100

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = None
        campaign.template = template

        # Create 51 contacts to trigger the batch_size=50 check
        contacts = []
        for j in range(51):
            c = MagicMock()
            c.id = uuid.uuid4()
            c.email = f"user{j}@test.com"
            c.first_name = f"User{j}"
            c.last_name = "Test"
            c.full_name = f"User{j} Test"
            c.custom_fields = None
            contacts.append(c)

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = contacts
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 50
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 50

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.commit = MagicMock()

        # On the first refresh (at i=50), change campaign status to paused
        def refresh_side_effect(obj):
            if obj is campaign:
                campaign.status = CampaignStatus.PAUSED.value

        session.refresh = MagicMock(side_effect=refresh_side_effect)
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        # Only 50 contacts processed before pause (the 51st triggers the check)
        assert result["queued"] == 50

    def test_campaign_completion_when_all_sent(self):
        """Cover lines 526-537: campaign completion check."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 1  # Only 1 recipient total

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = None
        campaign.template = template

        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "user@test.com"
        contact.first_name = "John"
        contact.last_name = "Doe"
        contact.full_name = "John Doe"
        contact.custom_fields = None

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 1
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 1  # >= total_recipients

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.refresh = MagicMock()
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result["queued"] == 1
        assert campaign.status == CampaignStatus.COMPLETED.value
        assert campaign.completed_at is not None

    def test_existing_sends_excludes_already_sent_contacts(self):
        """Cover line 387: existing_contact_ids is non-empty, triggering notin_ filter."""
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 2

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = None
        campaign.template = template

        # Only one new contact (the other was already sent)
        contact = MagicMock()
        contact.id = uuid.uuid4()
        contact.email = "new@test.com"
        contact.first_name = "New"
        contact.last_name = "User"
        contact.full_name = "New User"
        contact.custom_fields = None

        already_sent_contact_id = uuid.uuid4()

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign

        # existing_sends returns one already-sent contact ID
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = [(already_sent_contact_id,)]

        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = [contact]

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 2

        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 2

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.refresh = MagicMock()
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task") as mock_send_task,
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        assert result["queued"] == 1
        mock_send_task.delay.assert_called_once()

    def test_campaign_still_sending_after_batch_check(self):
        """Cover lines 407->418: campaign is still SENDING after batch refresh.

        When i=50 triggers the batch check (line 405) and the campaign is
        still in SENDING status, processing continues to the next contact
        (line 407 False branch -> line 418).
        """
        campaign = MagicMock()
        campaign.id = 1
        campaign.client_id = "app-one"
        campaign.status = CampaignStatus.SENDING.value
        campaign.group_id = 10
        campaign.subject_override = None
        campaign.from_email = "from@test.com"
        campaign.from_name = "Test"
        campaign.reply_to = None
        campaign.provider = "brevo"
        campaign.total_recipients = 200

        template = MagicMock()
        template.html_compiled = "<p>{{ first_name }}</p>"
        template.subject_template = "Hello {{ first_name }}"
        template.plain_text = None
        campaign.template = template

        # Create 52 contacts: 50 before batch check, then check passes (still
        # sending), then 2 more processed.
        contacts = []
        for j in range(52):
            c = MagicMock()
            c.id = uuid.uuid4()
            c.email = f"user{j}@test.com"
            c.first_name = f"User{j}"
            c.last_name = "Test"
            c.full_name = f"User{j} Test"
            c.custom_fields = None
            contacts.append(c)

        session = MagicMock()
        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = campaign
        existing_sends_result = MagicMock()
        existing_sends_result.fetchall.return_value = []
        contacts_result = MagicMock()
        contacts_result.scalars.return_value.all.return_value = contacts
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 52
        total_queued_result = MagicMock()
        total_queued_result.scalar.return_value = 52

        session.execute.side_effect = [
            campaign_result,
            existing_sends_result,
            contacts_result,
            sent_count_result,
            total_queued_result,
        ]
        session.flush = MagicMock()
        session.commit = MagicMock()

        # Campaign stays in SENDING status across all refreshes
        session.refresh = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.send.get_sync_db", return_value=ctx),
            patch("mailler.tasks.send.send_email_task"),
            patch("mailler.tasks.send.build_unsubscribe_url", return_value="http://unsub"),
            patch("mailler.tasks.send.settings") as mock_settings,
        ):
            mock_settings.default_from = "default@test.com"
            mock_settings.default_from_name = "Default"
            mock_settings.default_provider = ""
            mock_settings.campaign_batch_size = 50
            result = send_campaign_task(1)

        # All 52 contacts processed (batch check at i=50 passed, continued)
        assert result["queued"] == 52
        assert result["failed"] == 0


# ---------------------------------------------------------------------------
# Branch coverage: unrecognised status falls through all elifs
# ---------------------------------------------------------------------------


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

    def test_update_email_send_status_unknown_status(self):
        """_update_email_send_status with unknown status exercises elif-false branches."""
        db = MagicMock()
        email = MagicMock()
        email.metadata_ = {
            "email_send_id": str(uuid.uuid4()),
            "campaign_id": "1",
        }
        email_send = MagicMock()
        campaign = MagicMock(sent_count=0, failed_count=0)
        db.get.side_effect = [email_send, campaign]

        _update_email_send_status(db, email, "queued")

        # email_send should not have status set to sent or failed
        assert email_send.status != EmailSendStatus.SENT.value
        assert email_send.status != EmailSendStatus.FAILED.value
        # campaign counters unchanged
        assert campaign.sent_count == 0
        assert campaign.failed_count == 0
