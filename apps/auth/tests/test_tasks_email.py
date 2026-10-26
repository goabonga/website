# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.tasks.email — Email sending tasks."""

from unittest.mock import MagicMock, patch

import pytest
from auth.tasks.email import _send_via_mailler, _send_via_smtp, send_email
from celery.exceptions import Retry

# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------

TO = "recipient@example.com"
SUBJECT = "Test Subject"
BODY_HTML = "<p>Hello</p>"
BODY_TEXT = "Hello"


@pytest.fixture
def mock_settings():
    """Return a patched settings mock with sensible SMTP defaults."""
    with patch("auth.tasks.email.settings") as s:
        s.smtp_from = "noreply@example.com"
        s.smtp_host = "smtp.example.com"
        s.smtp_port = 587
        s.smtp_tls = True
        s.smtp_user = "user"
        s.smtp_password = "pass"
        s.email_backend = "smtp"
        s.mailler_url = ""
        yield s


# ── _send_via_smtp ────────────────────────────────────────────────────────


class TestSendViaSmtpImplicitTls:
    """1. Implicit TLS (port 465) with login."""

    @patch("auth.tasks.email.smtplib.SMTP_SSL")
    @patch("auth.tasks.email.smtplib.SMTP")
    def test_uses_smtp_ssl_on_port_465(self, mock_smtp, mock_smtp_ssl, mock_settings):
        mock_settings.smtp_port = 465
        mock_settings.smtp_tls = True
        smtp_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp_ssl.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML)

        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465)
        smtp_instance.login.assert_called_once_with("user", "pass")
        smtp_instance.sendmail.assert_called_once()
        mock_smtp.assert_not_called()
        assert result == {"status": "sent", "to": TO, "subject": SUBJECT, "backend": "smtp"}


class TestSendViaSmtpStarttls:
    """2. STARTTLS (port 587) with login."""

    @patch("auth.tasks.email.smtplib.SMTP_SSL")
    @patch("auth.tasks.email.smtplib.SMTP")
    def test_uses_starttls_on_port_587(self, mock_smtp, mock_smtp_ssl, mock_settings):
        mock_settings.smtp_port = 587
        mock_settings.smtp_tls = True
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML)

        mock_smtp.assert_called_once_with("smtp.example.com", 587)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("user", "pass")
        smtp_instance.sendmail.assert_called_once()
        mock_smtp_ssl.assert_not_called()
        assert result["status"] == "sent"


class TestSendViaSmtpStarttlsNoLogin:
    """3. STARTTLS without login (no user/password)."""

    @patch("auth.tasks.email.smtplib.SMTP_SSL")
    @patch("auth.tasks.email.smtplib.SMTP")
    def test_starttls_no_login(self, mock_smtp, mock_smtp_ssl, mock_settings):
        mock_settings.smtp_port = 587
        mock_settings.smtp_tls = True
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML)

        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_not_called()
        smtp_instance.sendmail.assert_called_once()
        assert result["status"] == "sent"


class TestSendViaSmtpNoTls:
    """4. No TLS at all."""

    @patch("auth.tasks.email.smtplib.SMTP_SSL")
    @patch("auth.tasks.email.smtplib.SMTP")
    def test_no_tls(self, mock_smtp, mock_smtp_ssl, mock_settings):
        mock_settings.smtp_port = 25
        mock_settings.smtp_tls = False
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML)

        mock_smtp.assert_called_once_with("smtp.example.com", 25)
        smtp_instance.starttls.assert_not_called()
        smtp_instance.login.assert_called_once_with("user", "pass")
        smtp_instance.sendmail.assert_called_once()
        mock_smtp_ssl.assert_not_called()
        assert result["status"] == "sent"


class TestSendViaSmtpWithTextBody:
    """5. With text body — both text and HTML parts attached."""

    @patch("auth.tasks.email.smtplib.SMTP")
    def test_text_body_attached(self, mock_smtp, mock_settings):
        mock_settings.smtp_port = 587
        mock_settings.smtp_tls = True
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML, body_text=BODY_TEXT)

        # sendmail was called (message built correctly)
        smtp_instance.sendmail.assert_called_once()
        call_args = smtp_instance.sendmail.call_args
        msg_string = call_args[0][2]
        assert "text/plain" in msg_string
        assert "text/html" in msg_string
        assert result["status"] == "sent"


class TestSendViaSmtpWithoutTextBody:
    """6. Without text body — only HTML part attached."""

    @patch("auth.tasks.email.smtplib.SMTP")
    def test_no_text_body(self, mock_smtp, mock_settings):
        mock_settings.smtp_port = 587
        mock_settings.smtp_tls = True
        smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = _send_via_smtp(TO, SUBJECT, BODY_HTML, body_text="")

        smtp_instance.sendmail.assert_called_once()
        call_args = smtp_instance.sendmail.call_args
        msg_string = call_args[0][2]
        # HTML part is always present
        assert "text/html" in msg_string
        # text/plain should NOT be present when body_text is empty
        # (MIMEMultipart "alternative" with only the HTML part)
        # Count occurrences — only the html attachment, no plain
        assert msg_string.count("text/plain") == 0
        assert result["status"] == "sent"


# ── _send_via_mailler ─────────────────────────────────────────────────────


class TestSendViaMailler:
    """7. Mailler backend success."""

    @patch("auth.tasks.email.settings")
    @patch("auth.services.mailler.get_mailler_client")
    def test_success(self, mock_get_client, mock_settings):
        mock_client = MagicMock()
        mock_client.send_email.return_value = {
            "status": "queued",
            "id": "msg-123",
            "task_id": "task-456",
        }
        mock_get_client.return_value = mock_client

        result = _send_via_mailler(TO, SUBJECT, BODY_HTML, body_text=BODY_TEXT)

        mock_client.send_email.assert_called_once_with(
            to_email=TO,
            subject=SUBJECT,
            html_content=BODY_HTML,
            text_content=BODY_TEXT,
            from_email=None,
            from_name=None,
            metadata={"source": "auth-service"},
        )
        assert result == {
            "status": "queued",
            "to": TO,
            "subject": SUBJECT,
            "backend": "mailler",
            "mailler_id": "msg-123",
            "task_id": "task-456",
        }

    @patch("auth.tasks.email.settings")
    @patch("auth.services.mailler.get_mailler_client")
    def test_empty_text_sends_none(self, mock_get_client, mock_settings):
        """When body_text is empty, text_content should be None."""
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"status": "queued"}
        mock_get_client.return_value = mock_client

        _send_via_mailler(TO, SUBJECT, BODY_HTML, body_text="")

        call_kwargs = mock_client.send_email.call_args[1]
        assert call_kwargs["text_content"] is None


# ── send_email (Celery task) ──────────────────────────────────────────────
#
# send_email is a Celery task with bind=True.  When called directly (e.g.
# send_email(to, subject, body_html)), Celery automatically injects `self`
# as the first argument.  We must NOT pass a mock_self manually; instead we
# patch attributes on the task object itself (retry, request, etc.).
# ---------------------------------------------------------------------------


class TestSendEmailMaillerBackendSuccess:
    """8. Mailler backend success via send_email task."""

    @patch("auth.tasks.email._get_platform_sender", return_value=(None, None))
    @patch("auth.tasks.email._send_via_mailler")
    @patch("auth.tasks.email.settings")
    def test_mailler_success(self, mock_settings, mock_mailler, mock_sender):
        mock_settings.email_backend = "mailler"
        mock_settings.mailler_url = "https://mailler.example.com"
        mock_mailler.return_value = {
            "status": "queued",
            "to": TO,
            "subject": SUBJECT,
            "backend": "mailler",
            "mailler_id": "msg-1",
            "task_id": "t-1",
        }

        result = send_email(TO, SUBJECT, BODY_HTML)

        mock_mailler.assert_called_once_with(TO, SUBJECT, BODY_HTML, "", None, None)
        assert result["backend"] == "mailler"
        assert result["status"] == "queued"


class TestSendEmailMaillerNoUrlFallsToSmtp:
    """9. Mailler backend with no URL falls back to SMTP."""

    @patch("auth.tasks.email._get_platform_sender", return_value=(None, None))
    @patch("auth.tasks.email._send_via_smtp")
    @patch("auth.tasks.email.settings")
    def test_falls_back_to_smtp(self, mock_settings, mock_smtp_fn, mock_sender):
        mock_settings.email_backend = "mailler"
        mock_settings.mailler_url = ""
        mock_settings.smtp_host = "smtp.example.com"
        mock_smtp_fn.return_value = {
            "status": "sent",
            "to": TO,
            "subject": SUBJECT,
            "backend": "smtp",
        }

        result = send_email(TO, SUBJECT, BODY_HTML)

        mock_smtp_fn.assert_called_once_with(TO, SUBJECT, BODY_HTML, "", None, None)
        assert result["backend"] == "smtp"
        assert result["status"] == "sent"


class TestSendEmailMaillerFailsRetries:
    """10. Mailler fails, task retries."""

    @patch("auth.tasks.email._send_via_mailler", side_effect=ConnectionError("mailler down"))
    @patch("auth.tasks.email.settings")
    def test_mailler_retry(self, mock_settings, mock_mailler):
        mock_settings.email_backend = "mailler"
        mock_settings.mailler_url = "https://mailler.example.com"

        with (
            patch.object(send_email, "retry", side_effect=Retry("retry")) as mock_retry,
            pytest.raises(Retry),
        ):
            send_email(TO, SUBJECT, BODY_HTML)

        mock_retry.assert_called_once()


class TestSendEmailMaillerMaxRetries:
    """11. Mailler fails max retries -- returns failed."""

    @patch("auth.tasks.email._send_via_mailler", side_effect=ConnectionError("mailler down"))
    @patch("auth.tasks.email.settings")
    def test_mailler_max_retries(self, mock_settings, mock_mailler):
        mock_settings.email_backend = "mailler"
        mock_settings.mailler_url = "https://mailler.example.com"

        with patch.object(send_email, "retry", side_effect=send_email.MaxRetriesExceededError()):
            result = send_email(TO, SUBJECT, BODY_HTML)

        assert result["status"] == "failed"
        assert result["backend"] == "mailler"
        assert result["error"] == "mailler down"
        assert result["to"] == TO
        assert result["subject"] == SUBJECT


class TestSendEmailSmtpBackendSuccess:
    """12. SMTP backend success."""

    @patch("auth.tasks.email._get_platform_sender", return_value=(None, None))
    @patch("auth.tasks.email._send_via_smtp")
    @patch("auth.tasks.email.settings")
    def test_smtp_success(self, mock_settings, mock_smtp_fn, mock_sender):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = "smtp.example.com"
        mock_smtp_fn.return_value = {
            "status": "sent",
            "to": TO,
            "subject": SUBJECT,
            "backend": "smtp",
        }

        result = send_email(TO, SUBJECT, BODY_HTML)

        mock_smtp_fn.assert_called_once_with(TO, SUBJECT, BODY_HTML, "", None, None)
        assert result["status"] == "sent"
        assert result["backend"] == "smtp"


class TestSendEmailSmtpNotConfigured:
    """13. SMTP not configured -- falls back to console log."""

    @patch("auth.tasks.email.settings")
    def test_console_fallback(self, mock_settings):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = ""

        result = send_email(TO, SUBJECT, BODY_HTML)

        assert result == {
            "status": "logged",
            "to": TO,
            "subject": SUBJECT,
            "backend": "console",
        }


class TestSendEmailSmtpFailsRetries:
    """14. SMTP fails, task retries."""

    @patch("auth.tasks.email._send_via_smtp", side_effect=OSError("connection refused"))
    @patch("auth.tasks.email.settings")
    def test_smtp_retry(self, mock_settings, mock_smtp_fn):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = "smtp.example.com"

        with (
            patch.object(send_email, "retry", side_effect=Retry("retry")) as mock_retry,
            pytest.raises(Retry),
        ):
            send_email(TO, SUBJECT, BODY_HTML)

        mock_retry.assert_called_once()


class TestSendEmailSmtpMaxRetries:
    """15. SMTP fails max retries -- returns failed."""

    @patch("auth.tasks.email._send_via_smtp", side_effect=OSError("connection refused"))
    @patch("auth.tasks.email.settings")
    def test_smtp_max_retries(self, mock_settings, mock_smtp_fn):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = "smtp.example.com"

        with patch.object(send_email, "retry", side_effect=send_email.MaxRetriesExceededError()):
            result = send_email(TO, SUBJECT, BODY_HTML)

        assert result["status"] == "failed"
        assert result["backend"] == "smtp"
        assert result["error"] == "connection refused"
        assert result["to"] == TO
        assert result["subject"] == SUBJECT


# ── _get_platform_sender / invalidate_platform_sender_cache ─────────────────


class TestGetPlatformSender:
    """Covers the platform-tenant sender lookup and its in-process cache."""

    def setup_method(self):
        from auth.tasks.email import invalidate_platform_sender_cache

        invalidate_platform_sender_cache()

    teardown_method = setup_method

    def _patched_engine(self, row):
        """Patch create_engine so ``conn.execute(...).first()`` yields ``row``."""
        conn = MagicMock()
        conn.execute.return_value.first.return_value = row
        engine = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        return patch("sqlalchemy.create_engine", return_value=engine), engine

    def test_reads_sender_from_platform_tenant(self):
        from auth.tasks.email import _get_platform_sender

        row_settings = {
            "email_sender_address": "noreply@acme.test",
            "email_sender_name": "Acme",
        }
        engine_patch, engine = self._patched_engine((row_settings,))
        with engine_patch:
            assert _get_platform_sender() == ("noreply@acme.test", "Acme")

        engine.dispose.assert_called_once()

    def test_result_is_cached(self):
        from auth.tasks.email import _get_platform_sender

        engine_patch, _ = self._patched_engine(({"email_sender_address": "a@b.test"},))
        with engine_patch:
            _get_platform_sender()

        # Second call must not touch the database at all.
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("re-queried")):
            assert _get_platform_sender() == ("a@b.test", None)

    def test_no_platform_tenant_row(self):
        from auth.tasks.email import _get_platform_sender

        engine_patch, _ = self._patched_engine(None)
        with engine_patch:
            assert _get_platform_sender() == (None, None)

    def test_row_with_empty_settings(self):
        from auth.tasks.email import _get_platform_sender

        engine_patch, _ = self._patched_engine((None,))
        with engine_patch:
            assert _get_platform_sender() == (None, None)

    def test_database_failure_is_swallowed(self):
        from auth.tasks.email import _get_platform_sender

        with patch("sqlalchemy.create_engine", side_effect=OSError("no db")):
            assert _get_platform_sender() == (None, None)


class TestInvalidatePlatformSenderCache:
    def test_clears_cache(self):
        from auth.tasks.email import _platform_sender_cache, invalidate_platform_sender_cache

        _platform_sender_cache["from_email"] = "stale@example.com"

        invalidate_platform_sender_cache()

        assert _platform_sender_cache == {}


# ── remaining branch coverage ───────────────────────────────────────────────


class TestSendViaSmtpImplicitTlsNoLogin:
    @patch("auth.tasks.email.smtplib.SMTP_SSL")
    def test_no_credentials_skips_login(self, mock_smtp_ssl, mock_settings):
        """Implicit TLS without SMTP credentials must not attempt a login."""
        mock_settings.smtp_port = 465
        mock_settings.smtp_tls = True
        mock_settings.smtp_user = None
        mock_settings.smtp_password = None

        smtp = MagicMock()
        mock_smtp_ssl.return_value.__enter__ = MagicMock(return_value=smtp)
        mock_smtp_ssl.return_value.__exit__ = MagicMock(return_value=False)

        _send_via_smtp(TO, SUBJECT, BODY_HTML)

        smtp.login.assert_not_called()
        smtp.sendmail.assert_called_once()


class TestSendEmailExplicitSender:
    @patch("auth.tasks.email._get_platform_sender")
    @patch("auth.tasks.email._send_via_smtp", return_value={"status": "sent"})
    @patch("auth.tasks.email.settings")
    def test_explicit_from_email_skips_platform_lookup(
        self, mock_settings, mock_smtp_fn, mock_sender
    ):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = "smtp.example.com"

        result = send_email(TO, SUBJECT, BODY_HTML, from_email="explicit@example.com")

        assert result == {"status": "sent"}
        mock_sender.assert_not_called()


class TestRetryReturningNormallyReraises:
    """When ``self.retry()`` returns instead of raising, the original error propagates."""

    @patch("auth.tasks.email._send_via_mailler", side_effect=ConnectionError("mailler down"))
    @patch("auth.tasks.email.settings")
    def test_mailler(self, mock_settings, mock_mailler):
        mock_settings.email_backend = "mailler"
        mock_settings.mailler_url = "https://mailler.example.com"

        with (
            patch.object(send_email, "retry", return_value=None),
            pytest.raises(ConnectionError, match="mailler down"),
        ):
            send_email(TO, SUBJECT, BODY_HTML)

    @patch("auth.tasks.email._send_via_smtp", side_effect=OSError("connection refused"))
    @patch("auth.tasks.email.settings")
    def test_smtp(self, mock_settings, mock_smtp_fn):
        mock_settings.email_backend = "smtp"
        mock_settings.smtp_host = "smtp.example.com"

        with (
            patch.object(send_email, "retry", return_value=None),
            pytest.raises(OSError, match="connection refused"),
        ):
            send_email(TO, SUBJECT, BODY_HTML)
