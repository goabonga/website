# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.services.providers.sendgrid module."""

from unittest.mock import MagicMock, patch

import httpx
from mailler.services.providers.sendgrid import SendGridProvider


class TestSendGridProviderProperties:
    """Tests for SendGridProvider properties."""

    def test_provider_name(self):
        provider = SendGridProvider(api_key="key")
        assert provider.provider_name == "sendgrid"

    def test_is_configured(self):
        assert SendGridProvider(api_key="key").is_configured is True
        assert SendGridProvider(api_key="").is_configured is False


class TestSendGridSendEmail:
    """Tests for SendGridProvider.send_email."""

    def test_not_configured(self):
        provider = SendGridProvider(api_key="")
        result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")
        assert result.success is False
        assert "not configured" in result.error_message

    def test_successful_send(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "sg-msg-123"}

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Subject", "<p>Hello</p>")

        assert result.success is True
        assert result.provider_message_id == "sg-msg-123"

    def test_send_with_plain_body(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "msg-456"}

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Subject", "<p>Hello</p>", plain_body="Hello")

        assert result.success is True
        # Verify plain text was inserted before HTML in content
        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        content = payload["content"]
        assert content[0]["type"] == "text/plain"
        assert content[1]["type"] == "text/html"

    def test_api_error_with_errors_array(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"errors":[{"message":"Invalid email"}]}'
        mock_response.json.return_value = {"errors": [{"message": "Invalid email"}]}

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "Invalid email" in result.error_message

    def test_api_error_without_errors_array(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.content = b""
        mock_response.json.return_value = {}

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False
        assert "500" in result.error_message

    def test_network_error(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.RequestError("timeout")
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False

    def test_unexpected_error(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = RuntimeError("unexpected")
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>")

        assert result.success is False

    def test_send_with_reply_to(self):
        provider = SendGridProvider(
            api_key="sg-key", default_from="f@t.com", default_from_name="Test"
        )

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.headers = {"X-Message-Id": "msg"}

        with patch("mailler.services.providers.sendgrid.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_cls.return_value = mock_client

            result = provider.send_email("to@t.com", "Sub", "<p>Body</p>", reply_to="reply@t.com")

        assert result.success is True
        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["reply_to"]["email"] == "reply@t.com"
