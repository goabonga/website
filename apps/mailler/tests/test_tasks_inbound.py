# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for inbound email tasks."""

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from mailler.models.inbound import InboundStatus
from mailler.tasks.inbound import (
    _save_attachment,
    _store_inbound_email,
    cleanup_expired_attachments,
    poll_inbound_emails,
    retry_failed_inbound,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_db_ctx(session):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# _save_attachment
# ---------------------------------------------------------------------------


class TestSaveAttachment:
    def test_saves_file(self, tmp_path):
        email_id = uuid.uuid4()
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_attachments_dir = str(tmp_path)
            result = _save_attachment(b"content", "test.txt", email_id)

        assert os.path.exists(result)
        assert Path(result).read_bytes() == b"content"

    def test_sanitizes_filename(self, tmp_path):
        email_id = uuid.uuid4()
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_attachments_dir = str(tmp_path)
            result = _save_attachment(b"data", "he llo/wor!ld.pdf", email_id)

        filename = os.path.basename(result)
        assert "/" not in filename
        assert " " not in filename
        assert "!" not in filename

    def test_empty_filename_becomes_attachment(self, tmp_path):
        email_id = uuid.uuid4()
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_attachments_dir = str(tmp_path)
            result = _save_attachment(b"data", "", email_id)

        assert "attachment" in os.path.basename(result)

    def test_handles_duplicate_filename(self, tmp_path):
        email_id = uuid.uuid4()
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_attachments_dir = str(tmp_path)
            # First save
            result1 = _save_attachment(b"data1", "file.txt", email_id)
            # Second save -- same filename
            result2 = _save_attachment(b"data2", "file.txt", email_id)

        assert result1 != result2
        assert os.path.exists(result1)
        assert os.path.exists(result2)


# ---------------------------------------------------------------------------
# _store_inbound_email
# ---------------------------------------------------------------------------


class TestStoreInboundEmail:
    def test_stores_new_email(self):
        parsed = MagicMock()
        parsed.message_id = "msg-123"
        parsed.in_reply_to = None
        parsed.from_email = "sender@test.com"
        parsed.from_name = "Sender"
        parsed.to = ["to@test.com"]
        parsed.cc = []
        parsed.reply_to_email = None
        parsed.reply_to_name = None
        parsed.subject = "Test"
        parsed.html_body = "<p>Hi</p>"
        parsed.text_body = "Hi"
        parsed.headers = {}
        parsed.sent_at_date = None
        parsed.attachments = []

        session = MagicMock()
        # First execute: duplicate check returns None
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.flush = MagicMock()
        session.commit = MagicMock()
        session.refresh = MagicMock()

        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = _store_inbound_email(parsed, "uid-1")

        inbound_email, attachments = result
        session.add.assert_called_once()
        assert attachments == []

    def test_detects_duplicate(self):
        parsed = MagicMock()
        parsed.message_id = "msg-dup"
        parsed.attachments = []

        existing = MagicMock()
        existing.id = uuid.uuid4()

        session = MagicMock()
        # First call: duplicate check returns existing
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = existing

        # Second call: fetch attachments
        att_result = MagicMock()
        att_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [dup_result, att_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            inbound_email, attachments = _store_inbound_email(parsed, "uid-2")

        assert inbound_email is existing
        session.add.assert_not_called()

    def test_stores_with_attachments(self, tmp_path):
        parsed = MagicMock()
        parsed.message_id = None  # No duplicate check
        parsed.in_reply_to = None
        parsed.from_email = "s@t.com"
        parsed.from_name = None
        parsed.to = []
        parsed.cc = []
        parsed.reply_to_email = None
        parsed.reply_to_name = None
        parsed.subject = "With att"
        parsed.html_body = None
        parsed.text_body = "text"
        parsed.headers = {}
        parsed.sent_at_date = None

        att = MagicMock()
        att.content = b"file-data"
        att.filename = "doc.pdf"
        att.content_type = "application/pdf"
        att.content_id = None
        parsed.attachments = [att]

        session = MagicMock()
        session.flush = MagicMock()
        session.commit = MagicMock()
        session.refresh = MagicMock()

        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
            patch("mailler.tasks.inbound._save_attachment", return_value="/tmp/doc.pdf"),
            patch("mailler.tasks.inbound.settings") as mock_settings,
        ):
            mock_settings.inbound_attachment_ttl = 3600
            inbound_email, attachments = _store_inbound_email(parsed, "uid-3")

        # InboundEmail + 1 InboundAttachment
        assert session.add.call_count == 2
        assert len(attachments) == 1


# ---------------------------------------------------------------------------
# poll_inbound_emails
# ---------------------------------------------------------------------------


class TestPollInboundEmails:
    def test_disabled(self):
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_enabled = False
            result = poll_inbound_emails()

        assert result["skipped"] is True
        assert "disabled" in result["reason"]

    def test_no_webhook_url(self):
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = ""
            result = poll_inbound_emails()

        assert result["skipped"] is True

    def test_mailbox_not_configured(self):
        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "https://hooks.example.test/inbound"
            mock_settings.protonmail_host = ""
            mock_settings.inbound_imap_port = 0
            mock_settings.inbound_attachments_dir = ""
            result = poll_inbound_emails()

        assert result == {"skipped": True, "reason": "mailbox not configured"}
        mock_connect.assert_not_called()

    def test_no_emails(self):
        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch("mailler.tasks.inbound.fetch_unseen_emails", return_value=[]),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Processed"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        assert result == {"processed": 0, "forwarded": 0, "failed": 0}

    def test_success_flow(self):
        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.status = InboundStatus.RECEIVED.value

        email_record = MagicMock()
        email_record.status = InboundStatus.RECEIVED.value
        email_record.retry_count = 0

        session = MagicMock()
        session.get.return_value = email_record
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch(
                "mailler.tasks.inbound.fetch_unseen_emails",
                return_value=[("uid1", b"raw-email")],
            ),
            patch("mailler.tasks.inbound.parse_email_bytes"),
            patch(
                "mailler.tasks.inbound._store_inbound_email",
                return_value=(inbound_email, []),
            ),
            patch(
                "mailler.tasks.inbound.build_brevo_payload",
                return_value={"key": "val"},
            ),
            patch(
                "mailler.tasks.inbound.deliver_webhook",
                return_value=(200, True),
            ),
            patch("mailler.tasks.inbound.move_to_folder"),
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Processed"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        assert result["processed"] == 1
        assert result["forwarded"] == 1
        assert result["failed"] == 0

    def test_webhook_failure(self):
        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.status = InboundStatus.RECEIVED.value

        email_record = MagicMock()
        email_record.retry_count = 0

        session = MagicMock()
        session.get.return_value = email_record
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch(
                "mailler.tasks.inbound.fetch_unseen_emails",
                return_value=[("uid1", b"raw")],
            ),
            patch("mailler.tasks.inbound.parse_email_bytes"),
            patch(
                "mailler.tasks.inbound._store_inbound_email",
                return_value=(inbound_email, []),
            ),
            patch("mailler.tasks.inbound.build_brevo_payload", return_value={}),
            patch(
                "mailler.tasks.inbound.deliver_webhook",
                return_value=(500, False),
            ),
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Processed"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        assert result["failed"] == 1
        assert result["forwarded"] == 0

    def test_already_forwarded_skips(self):
        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.status = InboundStatus.FORWARDED.value

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch(
                "mailler.tasks.inbound.fetch_unseen_emails",
                return_value=[("uid1", b"raw")],
            ),
            patch("mailler.tasks.inbound.parse_email_bytes"),
            patch(
                "mailler.tasks.inbound._store_inbound_email",
                return_value=(inbound_email, []),
            ),
            patch("mailler.tasks.inbound.move_to_folder") as mock_move,
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Done"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        # Moved but not counted as forwarded (was already)
        mock_move.assert_called_once()
        assert result["forwarded"] == 0

    def test_imap_error(self):
        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch(
                "mailler.tasks.inbound.connect",
                side_effect=Exception("IMAP connection refused"),
            ),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Done"

            result = poll_inbound_emails()

        assert "error" in result
        assert "IMAP" in result["error"]

    def test_processing_exception(self):
        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch(
                "mailler.tasks.inbound.fetch_unseen_emails",
                return_value=[("uid1", b"raw")],
            ),
            patch(
                "mailler.tasks.inbound.parse_email_bytes",
                side_effect=Exception("parse fail"),
            ),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Done"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        assert result["failed"] == 1

    def test_email_record_not_found_in_db(self):
        """Cover lines 224->240: email_record is None after db.get().

        When the InboundEmail record cannot be found during webhook status
        update, the code skips status update and checks the success flag.
        """
        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.status = InboundStatus.RECEIVED.value

        session = MagicMock()
        # db.get returns None (email record not found)
        session.get.return_value = None
        session.commit = MagicMock()
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect") as mock_connect,
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch(
                "mailler.tasks.inbound.fetch_unseen_emails",
                return_value=[("uid1", b"raw-email")],
            ),
            patch("mailler.tasks.inbound.parse_email_bytes"),
            patch(
                "mailler.tasks.inbound._store_inbound_email",
                return_value=(inbound_email, []),
            ),
            patch(
                "mailler.tasks.inbound.build_brevo_payload",
                return_value={"key": "val"},
            ),
            patch(
                "mailler.tasks.inbound.deliver_webhook",
                return_value=(200, True),
            ),
            patch("mailler.tasks.inbound.move_to_folder") as mock_move,
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Processed"
            mock_connect.return_value = MagicMock()

            result = poll_inbound_emails()

        # email_record is None so no status update happened, forwarded stays 0
        # But success is True so move_to_folder is still called
        assert result["processed"] == 1
        assert result["forwarded"] == 0
        mock_move.assert_called_once()

    def test_imap_logout_exception(self):
        """Cover lines 262-263: imap.logout() raises an exception.

        The except block catches the exception and passes silently.
        """
        mock_imap = MagicMock()
        mock_imap.logout.side_effect = Exception("Logout failed")

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.connect", return_value=mock_imap),
            patch("mailler.tasks.inbound.ensure_folder_exists"),
            patch("mailler.tasks.inbound.fetch_unseen_emails", return_value=[]),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"
            mock_settings.inbound_processed_folder = "Processed"

            result = poll_inbound_emails()

        # Should complete normally despite logout failure
        assert result == {"processed": 0, "forwarded": 0, "failed": 0}
        mock_imap.logout.assert_called_once()


# ---------------------------------------------------------------------------
# retry_failed_inbound
# ---------------------------------------------------------------------------


class TestRetryFailedInbound:
    def test_disabled(self):
        with patch("mailler.tasks.inbound.settings") as mock_settings:
            mock_settings.inbound_enabled = False
            mock_settings.inbound_webhook_url = ""
            result = retry_failed_inbound()

        assert result == {"skipped": True}

    def test_retries_and_succeeds(self):
        inbound = MagicMock()
        inbound.id = uuid.uuid4()
        inbound.retry_count = 1

        session = MagicMock()

        # First execute: failed emails
        failed_result = MagicMock()
        failed_result.scalars.return_value.all.return_value = [inbound]

        # Second execute: attachments
        att_result = MagicMock()
        att_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [failed_result, att_result]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
            patch("mailler.tasks.inbound.build_brevo_payload", return_value={}),
            patch("mailler.tasks.inbound.deliver_webhook", return_value=(200, True)),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"

            result = retry_failed_inbound()

        assert result == {"retried": 1, "succeeded": 1}
        assert inbound.status == InboundStatus.FORWARDED.value
        assert inbound.error_message is None

    def test_retries_and_fails(self):
        inbound = MagicMock()
        inbound.id = uuid.uuid4()
        inbound.retry_count = 1

        session = MagicMock()
        failed_result = MagicMock()
        failed_result.scalars.return_value.all.return_value = [inbound]

        att_result = MagicMock()
        att_result.scalars.return_value.all.return_value = []

        session.execute.side_effect = [failed_result, att_result]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
            patch("mailler.tasks.inbound.build_brevo_payload", return_value={}),
            patch("mailler.tasks.inbound.deliver_webhook", return_value=(503, False)),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"

            result = retry_failed_inbound()

        assert result == {"retried": 1, "succeeded": 0}
        assert inbound.retry_count == 2

    def test_no_failed_emails(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.settings") as mock_settings,
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
        ):
            mock_settings.inbound_enabled = True
            mock_settings.inbound_webhook_url = "http://hook"

            result = retry_failed_inbound()

        assert result == {"retried": 0, "succeeded": 0}


# ---------------------------------------------------------------------------
# cleanup_expired_attachments
# ---------------------------------------------------------------------------


class TestCleanupExpiredAttachments:
    def test_no_expired(self):
        session = MagicMock()
        session.execute.return_value.scalars.return_value.all.return_value = []
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = cleanup_expired_attachments()

        assert result == {"deleted_files": 0, "deleted_records": 0}

    def test_deletes_files_and_records(self, tmp_path):
        # Create a temp file to delete
        att_file = tmp_path / "test.txt"
        att_file.write_text("data")

        att = MagicMock()
        att.file_path = str(att_file)

        session = MagicMock()
        # First execute: find expired
        expired_result = MagicMock()
        expired_result.scalars.return_value.all.return_value = [att]

        # Second execute: delete statement
        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute.side_effect = [expired_result, delete_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = cleanup_expired_attachments()

        assert result == {"deleted_files": 1, "deleted_records": 1}
        assert not att_file.exists()

    def test_handles_missing_file(self):
        att = MagicMock()
        att.file_path = "/nonexistent/file.txt"

        session = MagicMock()
        expired_result = MagicMock()
        expired_result.scalars.return_value.all.return_value = [att]

        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute.side_effect = [expired_result, delete_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = cleanup_expired_attachments()

        # File didn't exist so deleted_files is 0, but record still deleted
        assert result["deleted_files"] == 0
        assert result["deleted_records"] == 1

    def test_cleans_empty_parent_dir(self, tmp_path):
        # Create parent dir and file
        parent = tmp_path / "email-123"
        parent.mkdir()
        att_file = parent / "doc.pdf"
        att_file.write_text("data")

        att = MagicMock()
        att.file_path = str(att_file)

        session = MagicMock()
        expired_result = MagicMock()
        expired_result.scalars.return_value.all.return_value = [att]

        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute.side_effect = [expired_result, delete_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = cleanup_expired_attachments()

        assert result["deleted_files"] == 1
        # Parent dir should also be removed (was empty after file delete)
        assert not parent.exists()

    def test_os_remove_raises_oserror(self, tmp_path):
        """Cover lines 368-369: os.remove raises OSError, logged as warning."""
        att_file = tmp_path / "locked.txt"
        att_file.write_text("data")

        att = MagicMock()
        att.file_path = str(att_file)

        session = MagicMock()
        expired_result = MagicMock()
        expired_result.scalars.return_value.all.return_value = [att]

        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute.side_effect = [expired_result, delete_result]
        ctx = _make_sync_db_ctx(session)

        with (
            patch("mailler.tasks.inbound.get_sync_db", return_value=ctx),
            patch("os.path.exists", return_value=True),
            patch("os.remove", side_effect=OSError("Permission denied")),
        ):
            result = cleanup_expired_attachments()

        # File deletion failed, so deleted_files stays 0
        assert result["deleted_files"] == 0
        # DB records are still cleaned up
        assert result["deleted_records"] == 1

    def test_non_empty_parent_dir_not_removed(self, tmp_path):
        """Cover lines 366->357: parent dir is not empty after file deletion.

        When the parent directory still contains other files after deletion,
        os.rmdir is not called and the loop continues to the next attachment.
        """
        parent = tmp_path / "email-456"
        parent.mkdir()
        att_file = parent / "doc1.pdf"
        att_file.write_text("data1")
        # Another file in the same directory -- prevents rmdir
        other_file = parent / "doc2.pdf"
        other_file.write_text("data2")

        att = MagicMock()
        att.file_path = str(att_file)

        session = MagicMock()
        expired_result = MagicMock()
        expired_result.scalars.return_value.all.return_value = [att]

        delete_result = MagicMock()
        delete_result.rowcount = 1

        session.execute.side_effect = [expired_result, delete_result]
        ctx = _make_sync_db_ctx(session)

        with patch("mailler.tasks.inbound.get_sync_db", return_value=ctx):
            result = cleanup_expired_attachments()

        assert result["deleted_files"] == 1
        assert result["deleted_records"] == 1
        # Parent dir should NOT be removed (still has doc2.pdf)
        assert parent.exists()
        assert other_file.exists()
