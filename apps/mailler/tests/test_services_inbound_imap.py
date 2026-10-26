# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.inbound.imap_client module."""

from unittest.mock import MagicMock, patch

SETTINGS_PATH = "mailler.services.inbound.imap_client.settings"


class TestConnect:
    """Tests for connect()."""

    def test_successful_connection(self):
        mock_imap = MagicMock()

        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.imap_client.imaplib.IMAP4", return_value=mock_imap),
        ):
            ms.protonmail_host = "127.0.0.1"
            ms.inbound_imap_port = 1143
            ms.protonmail_user = "user"
            ms.protonmail_password = "pass"

            from mailler.services.inbound.imap_client import connect

            result = connect()

        assert result is mock_imap
        mock_imap.starttls.assert_called_once()
        mock_imap.login.assert_called_once_with("user", "pass")

    def test_connection_error(self):
        with (
            patch(SETTINGS_PATH) as ms,
            patch(
                "mailler.services.inbound.imap_client.imaplib.IMAP4",
                side_effect=OSError("connection refused"),
            ),
        ):
            ms.protonmail_host = "127.0.0.1"
            ms.inbound_imap_port = 1143

            from mailler.services.inbound.imap_client import connect

            try:
                connect()
                raise AssertionError("Should have raised")
            except OSError:
                pass


class TestEnsureFolderExists:
    """Tests for ensure_folder_exists()."""

    def test_folder_exists(self):
        from mailler.services.inbound.imap_client import ensure_folder_exists

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])

        ensure_folder_exists(mock_imap, "Processed")

        mock_imap.create.assert_not_called()
        # Should go back to INBOX
        assert mock_imap.select.call_count == 2
        mock_imap.select.assert_called_with("INBOX")

    def test_folder_missing_creates_it(self):
        from mailler.services.inbound.imap_client import ensure_folder_exists

        mock_imap = MagicMock()
        mock_imap.select.side_effect = [("NO", [None]), ("OK", [b"1"])]

        ensure_folder_exists(mock_imap, "NewFolder")

        mock_imap.create.assert_called_once_with("NewFolder")


class TestFetchUnseenEmails:
    """Tests for fetch_unseen_emails()."""

    def test_no_unseen(self):
        from mailler.services.inbound.imap_client import fetch_unseen_emails

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("OK", [b""])

        result = fetch_unseen_emails(mock_imap)
        assert result == []

    def test_search_not_ok(self):
        from mailler.services.inbound.imap_client import fetch_unseen_emails

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("NO", [None])

        result = fetch_unseen_emails(mock_imap)
        assert result == []

    def test_returns_emails(self):
        from mailler.services.inbound.imap_client import fetch_unseen_emails

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])

        raw_email = b"From: test@test.com\r\nSubject: Hi\r\n\r\nHello"

        def uid_side_effect(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1 2"])
            if cmd == "fetch":
                return ("OK", [(b"1 (RFC822 {100}", raw_email)])
            return ("OK", [None])

        mock_imap.uid.side_effect = uid_side_effect

        result = fetch_unseen_emails(mock_imap)
        assert len(result) == 2
        assert result[0][0] == "1"
        assert result[0][1] == raw_email

    def test_skips_failed_fetch(self):
        from mailler.services.inbound.imap_client import fetch_unseen_emails

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])

        def uid_side_effect(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1"])
            if cmd == "fetch":
                return ("NO", [None])
            return ("OK", [None])

        mock_imap.uid.side_effect = uid_side_effect

        result = fetch_unseen_emails(mock_imap)
        assert result == []

    def test_skips_non_bytes_payload(self):
        """Cover branch line 74->69: raw_email is not bytes, skip and continue loop."""
        from mailler.services.inbound.imap_client import fetch_unseen_emails

        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"1"])

        def uid_side_effect(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1"])
            if cmd == "fetch":
                # Return a non-bytes payload (string instead of bytes)
                return ("OK", [(b"1 (RFC822 {100}", "not-bytes-payload")])
            return ("OK", [None])

        mock_imap.uid.side_effect = uid_side_effect

        result = fetch_unseen_emails(mock_imap)
        assert result == []


class TestMoveToFolder:
    """Tests for move_to_folder()."""

    def test_successful_move(self):
        from mailler.services.inbound.imap_client import move_to_folder

        mock_imap = MagicMock()
        mock_imap.uid.return_value = ("OK", [None])

        result = move_to_folder(mock_imap, "123", "Processed")

        assert result is True
        mock_imap.expunge.assert_called_once()

    def test_copy_failure(self):
        from mailler.services.inbound.imap_client import move_to_folder

        mock_imap = MagicMock()

        def uid_side_effect(cmd, *args):
            if cmd == "copy":
                return ("NO", [None])
            return ("OK", [None])

        mock_imap.uid.side_effect = uid_side_effect

        result = move_to_folder(mock_imap, "123", "Processed")
        assert result is False

    def test_imap_error(self):
        import imaplib

        from mailler.services.inbound.imap_client import move_to_folder

        mock_imap = MagicMock()
        mock_imap.uid.side_effect = imaplib.IMAP4.error("IMAP error")

        result = move_to_folder(mock_imap, "123", "Processed")
        assert result is False
