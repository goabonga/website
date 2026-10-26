# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for Amazon SES/SNS webhook proxy."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from webhooks.routes.ses import get_internal_client, ses_webhook


class TestGetInternalClient(unittest.TestCase):
    """Tests for get_internal_client()."""

    def test_with_socket(self):
        """Returns client with UDS transport when socket is configured."""
        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_with_url(self):
        """Returns client with base_url when URL is configured."""
        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = ""
            mock_settings.ses_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)
            self.assertEqual(str(client.base_url), "http://internal:8000")

    def test_socket_takes_priority_over_url(self):
        """Socket transport is used when both socket and URL are configured."""
        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_no_socket_no_url_raises(self):
        """Raises ValueError when neither socket nor URL is configured."""
        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = ""
            mock_settings.ses_internal_api_url = ""
            with self.assertRaises(ValueError):
                get_internal_client()


class TestSesWebhook(unittest.IsolatedAsyncioTestCase):
    """Tests for ses_webhook() endpoint."""

    async def test_not_configured_returns_503(self):
        """Returns 503 when neither socket nor URL is configured."""
        mock_request = AsyncMock()

        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = ""
            mock_settings.ses_internal_api_url = ""
            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.body, b"Service unavailable")

    async def test_empty_body_returns_200(self):
        """Returns 200 on empty body."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b""

        with patch("webhooks.routes.ses.settings") as mock_settings:
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 200)

    async def test_success_returns_internal_response(self):
        """Returns internal API status code and content on success."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b'{"ok": true}')

    async def test_success_with_url_only(self):
        """Works when only ses_internal_api_url is configured (no socket)."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = ""
            mock_settings.ses_internal_api_url = "http://internal:8000"
            mock_settings.ses_internal_api_token = ""

            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 200)

    async def test_forwards_correct_path_and_body(self):
        """Verifies correct path, body, and Content-Type are forwarded."""
        mock_request = AsyncMock()
        payload = b'{"Type": "Notification", "Message": "{}"}'
        mock_request.body.return_value = payload
        mock_request.headers = {"Content-Type": "text/plain"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            await ses_webhook(mock_request)
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            self.assertEqual(call_kwargs[0][0], "/webhooks/ses")
            self.assertEqual(call_kwargs[1]["content"], payload)
            self.assertEqual(call_kwargs[1]["headers"]["Content-Type"], "text/plain")

    async def test_forwards_sns_headers(self):
        """Forwards SNS-specific headers when present."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {
            "Content-Type": "text/plain",
            "x-amz-sns-message-type": "Notification",
            "x-amz-sns-message-id": "msg-123",
            "x-amz-sns-topic-arn": "arn:aws:sns:us-east-1:123:topic",
            "x-amz-sns-subscription-arn": "arn:aws:sns:us-east-1:123:topic:sub-456",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            await ses_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertEqual(headers["x-amz-sns-message-type"], "Notification")
            self.assertEqual(headers["x-amz-sns-message-id"], "msg-123")
            self.assertEqual(headers["x-amz-sns-topic-arn"], "arn:aws:sns:us-east-1:123:topic")
            self.assertEqual(
                headers["x-amz-sns-subscription-arn"], "arn:aws:sns:us-east-1:123:topic:sub-456"
            )

    async def test_missing_sns_headers_not_forwarded(self):
        """Only forwards SNS headers that are present."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            await ses_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertEqual(headers, {"Content-Type": "application/json"})

    async def test_connect_error_returns_502(self):
        """Returns 502 when internal API connection fails."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.body, b"Bad gateway")

    async def test_general_exception_returns_500(self):
        """Returns 500 on unexpected exception."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = RuntimeError("Unexpected error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.body, b"Internal server error")

    async def test_internal_error_status_forwarded(self):
        """Returns internal API error status code as-is."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b"Bad request"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            response = await ses_webhook(mock_request)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.body, b"Bad request")

    async def test_default_content_type_when_missing(self):
        """Uses text/plain as default Content-Type when header is missing."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            await ses_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Content-Type"], "text/plain")

    async def test_forwards_authorization_header_with_token(self):
        """Forwards Authorization header when token is configured."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = "my-token"

            await ses_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer my-token")

    async def test_no_authorization_header_without_token(self):
        """Does not send Authorization header when token is empty."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"Type": "Notification"}'
        mock_request.headers = {"Content-Type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.ses.settings") as mock_settings,
            patch("webhooks.routes.ses.get_internal_client", return_value=mock_client),
        ):
            mock_settings.ses_internal_api_socket = "/tmp/ses.sock"
            mock_settings.ses_internal_api_url = ""
            mock_settings.ses_internal_api_token = ""

            await ses_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertNotIn("Authorization", call_kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
