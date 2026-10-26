# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.providers.protonmail module."""

import smtplib
from unittest.mock import MagicMock, patch

from mailler.services.providers.protonmail import ProtonmailProvider


class TestProtonmailProviderProperties:
    """Tests for ProtonmailProvider properties."""

    def test_provider_name(self):
        provider = ProtonmailProvider(host="h", port=25, username="u", password="p")
        assert provider.provider_name == "protonmail"

    def test_is_configured(self):
        assert (
            ProtonmailProvider(host="h", port=25, username="u", password="p").is_configured is True
        )

    def test_not_configured_missing_host(self):
        with patch("mailler.services.providers.protonmail.settings") as mock_settings:
            mock_settings.protonmail_host = ""
            mock_settings.protonmail_port = 25
            mock_settings.protonmail_user = "u"
            mock_settings.protonmail_password = "p"
            mock_settings.default_from = "f@t.com"
            mock_settings.default_from_name = "T"
            provider = ProtonmailProvider(host="", port=25, username="u", password="p")
        assert provider.is_configured is False

    def test_not_configured_missing_password(self):
        with patch("mailler.services.providers.protonmail.settings") as mock_settings:
            mock_settings.protonmail_host = "h"
            mock_settings.protonmail_port = 25
            mock_settings.protonmail_user = "u"
            mock_settings.protonmail_password = ""
            mock_settings.default_from = "f@t.com"
            mock_settings.default_from_name = "T"
            provider = ProtonmailProvider(host="h", port=25, username="u", password="")
        assert provider.is_configured is False


class TestProtonmailFormatAddress:
    """Tests for ProtonmailProvider._format_address."""

    def test_with_name(self):
        provider = ProtonmailProvider(host="h", port=25, username="u", password="p")
        assert provider._format_address("Test", "test@t.com") == "Test <test@t.com>"

    def test_without_name(self):
        provider = ProtonmailProvider(host="h", port=25, username="u", password="p")
        assert provider._format_address(None, "test@t.com") == "test@t.com"


class TestProtonmailSendEmail:
    """Tests for ProtonmailProvider.send_email."""

    def test_not_configured(self):
        provider = ProtonmailProvider(host="", port=0, username="", password="")
        result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")
        assert result.success is False
        assert "not configured" in result.error_message

    def test_successful_send(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="pass",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email("to@t.com", "Subject", "<p>Hello</p>")

        assert result.success is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()

    def test_send_with_plain_body_and_reply_to(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="pass",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email(
                "to@t.com",
                "Sub",
                "<p>Hi</p>",
                plain_body="Hi",
                reply_to="reply@t.com",
            )

        assert result.success is True

    def test_auth_error(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="wrong",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b"Authentication failed"
            )
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "authentication failed" in result.error_message.lower()

    def test_recipient_refused(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="pass",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.sendmail.side_effect = smtplib.SMTPRecipientsRefused(
                {"to@t.com": (550, b"User unknown")}
            )
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "refused" in result.error_message.lower()

    def test_smtp_exception(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="pass",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.sendmail.side_effect = smtplib.SMTPException("SMTP error")
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False

    def test_unexpected_error(self):
        provider = ProtonmailProvider(
            host="localhost",
            port=1025,
            username="user",
            password="pass",
            default_from="from@t.com",
            default_from_name="Test",
        )

        with patch("mailler.services.providers.protonmail.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__ = MagicMock(side_effect=RuntimeError("unexpected"))
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
