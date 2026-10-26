# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.inbound.webhook module."""

import uuid
from unittest.mock import MagicMock, patch

import httpx

SETTINGS_PATH = "mailler.services.inbound.webhook.settings"


class TestGenerateSignature:
    """Tests for _generate_signature()."""

    def test_generates_hex_signature(self):
        from mailler.services.inbound.webhook import _generate_signature

        sig = _generate_signature(b"test payload", "my-secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest

    def test_different_payloads_different_sigs(self):
        from mailler.services.inbound.webhook import _generate_signature

        sig1 = _generate_signature(b"payload1", "secret")
        sig2 = _generate_signature(b"payload2", "secret")
        assert sig1 != sig2


class TestBuildBrevoPayload:
    """Tests for build_brevo_payload()."""

    def test_basic_payload(self):
        from mailler.services.inbound.webhook import build_brevo_payload

        email_id = uuid.uuid4()
        inbound_email = MagicMock()
        inbound_email.id = email_id
        inbound_email.from_email = "sender@test.com"
        inbound_email.from_name = "Sender"
        inbound_email.to_emails = [{"Address": "to@test.com", "Name": "To"}]
        inbound_email.cc_emails = []
        inbound_email.reply_to_email = None
        inbound_email.reply_to_name = None
        inbound_email.message_id = "<msg@test.com>"
        inbound_email.in_reply_to = None
        inbound_email.sent_at_date = "2024-01-01"
        inbound_email.subject = "Test Subject"
        inbound_email.html_body = "<p>Hello</p>"
        inbound_email.text_body = "Hello"
        inbound_email.spam_score = 0.0
        inbound_email.headers = {"X-Custom": "val"}

        payload = build_brevo_payload(inbound_email, [])

        assert len(payload.items) == 1
        item = payload.items[0]
        assert item.From.Address == "sender@test.com"
        assert item.Subject == "Test Subject"
        assert str(email_id) in item.Uuid

    def test_with_attachments(self):
        from mailler.services.inbound.webhook import build_brevo_payload

        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.from_email = "a@t.com"
        inbound_email.from_name = None
        inbound_email.to_emails = [{"Address": "b@t.com", "Name": None}]
        inbound_email.cc_emails = []
        inbound_email.reply_to_email = None
        inbound_email.reply_to_name = None
        inbound_email.message_id = ""
        inbound_email.in_reply_to = None
        inbound_email.sent_at_date = ""
        inbound_email.subject = "Sub"
        inbound_email.html_body = None
        inbound_email.text_body = "text"
        inbound_email.spam_score = 0.0
        inbound_email.headers = {}

        att = MagicMock()
        att.filename = "doc.pdf"
        att.content_type = "application/pdf"
        att.content_length = 1024
        att.content_id = ""
        att.download_token = uuid.uuid4()

        payload = build_brevo_payload(inbound_email, [att])

        assert len(payload.items[0].Attachments) == 1
        assert payload.items[0].Attachments[0].Name == "doc.pdf"

    def test_with_reply_to(self):
        from mailler.services.inbound.webhook import build_brevo_payload

        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.from_email = "a@t.com"
        inbound_email.from_name = None
        inbound_email.to_emails = [{"Address": "b@t.com", "Name": None}]
        inbound_email.cc_emails = [{"Address": "c@t.com", "Name": "CC"}]
        inbound_email.reply_to_email = "reply@t.com"
        inbound_email.reply_to_name = "Reply"
        inbound_email.message_id = ""
        inbound_email.in_reply_to = None
        inbound_email.sent_at_date = ""
        inbound_email.subject = "Sub"
        inbound_email.html_body = None
        inbound_email.text_body = "text"
        inbound_email.spam_score = 0.0
        inbound_email.headers = {}

        payload = build_brevo_payload(inbound_email, [])

        assert payload.items[0].ReplyTo.Address == "reply@t.com"
        assert len(payload.items[0].Cc) == 1

    def test_markdown_from_html(self):
        from mailler.services.inbound.webhook import build_brevo_payload

        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.from_email = "a@t.com"
        inbound_email.from_name = None
        inbound_email.to_emails = []
        inbound_email.cc_emails = []
        inbound_email.reply_to_email = None
        inbound_email.reply_to_name = None
        inbound_email.message_id = ""
        inbound_email.in_reply_to = None
        inbound_email.sent_at_date = ""
        inbound_email.subject = "Sub"
        inbound_email.html_body = "<p>Markdown source</p>"
        inbound_email.text_body = None
        inbound_email.spam_score = 0.0
        inbound_email.headers = {}

        payload = build_brevo_payload(inbound_email, [])

        assert payload.items[0].ExtractedMarkdownMessage != ""

    def test_no_html_and_no_text_body(self):
        """Cover branch line 77->81: both html_body and text_body are falsy."""
        from mailler.services.inbound.webhook import build_brevo_payload

        inbound_email = MagicMock()
        inbound_email.id = uuid.uuid4()
        inbound_email.from_email = "a@t.com"
        inbound_email.from_name = None
        inbound_email.to_emails = [{"Address": "b@t.com", "Name": None}]
        inbound_email.cc_emails = []
        inbound_email.reply_to_email = None
        inbound_email.reply_to_name = None
        inbound_email.message_id = ""
        inbound_email.in_reply_to = None
        inbound_email.sent_at_date = ""
        inbound_email.subject = "Empty body"
        inbound_email.html_body = None
        inbound_email.text_body = None
        inbound_email.spam_score = 0.0
        inbound_email.headers = {}

        payload = build_brevo_payload(inbound_email, [])

        assert payload.items[0].ExtractedMarkdownMessage == ""
        assert payload.items[0].RawHtmlBody is None
        assert payload.items[0].RawTextBody is None


class TestDeliverWebhook:
    """Tests for deliver_webhook()."""

    def test_no_url_configured(self):
        with patch(SETTINGS_PATH) as ms:
            ms.inbound_webhook_url = ""

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            status, success = deliver_webhook(payload)

        assert status == 0
        assert success is False

    def test_successful_delivery(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.webhook.httpx.Client") as mock_client_cls,
        ):
            ms.inbound_webhook_url = "https://hooks.example.com/inbound"
            ms.inbound_webhook_secret = ""

            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            payload.model_dump_json.return_value = '{"items": []}'

            status, success = deliver_webhook(payload)

        assert status == 200
        assert success is True

    def test_delivery_with_signature(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.webhook.httpx.Client") as mock_client_cls,
        ):
            ms.inbound_webhook_url = "https://hooks.example.com/inbound"
            ms.inbound_webhook_secret = "webhook-secret"

            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            payload.model_dump_json.return_value = '{"items": []}'

            status, success = deliver_webhook(payload)

        # Verify signature header was included
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "X-Webhook-Signature" in headers

    def test_non_2xx_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.webhook.httpx.Client") as mock_client_cls,
        ):
            ms.inbound_webhook_url = "https://hooks.example.com/inbound"
            ms.inbound_webhook_secret = ""

            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            payload.model_dump_json.return_value = '{"items": []}'

            status, success = deliver_webhook(payload)

        assert status == 500
        assert success is False

    def test_timeout_error(self):
        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.webhook.httpx.Client") as mock_client_cls,
        ):
            ms.inbound_webhook_url = "https://hooks.example.com/inbound"
            ms.inbound_webhook_secret = ""

            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            payload.model_dump_json.return_value = '{"items": []}'

            status, success = deliver_webhook(payload)

        assert status == 0
        assert success is False

    def test_request_error(self):
        with (
            patch(SETTINGS_PATH) as ms,
            patch("mailler.services.inbound.webhook.httpx.Client") as mock_client_cls,
        ):
            ms.inbound_webhook_url = "https://hooks.example.com/inbound"
            ms.inbound_webhook_secret = ""

            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.RequestError("connection failed")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            from mailler.services.inbound.webhook import deliver_webhook

            payload = MagicMock()
            payload.model_dump_json.return_value = '{"items": []}'

            status, success = deliver_webhook(payload)

        assert status == 0
        assert success is False
