# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for GitHub webhook proxy."""

import hashlib
import hmac
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from webhooks.routes.github import (
    get_internal_client,
    github_webhook,
    verify_github_signature,
)


class TestVerifyGithubSignature(unittest.TestCase):
    """Tests for verify_github_signature()."""

    def test_valid_signature(self):
        """Returns True when HMAC signature is valid."""
        secret = "test-secret"
        payload = b'{"action": "push"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        result = verify_github_signature(payload, sig, secret)
        self.assertTrue(result)

    def test_invalid_signature(self):
        """Returns False when HMAC signature does not match."""
        result = verify_github_signature(b"payload", "sha256=0000deadbeef", "secret")
        self.assertFalse(result)

    def test_missing_signature_returns_false(self):
        """Returns False when signature is empty."""
        result = verify_github_signature(b"payload", "", "secret")
        self.assertFalse(result)

    def test_missing_sha256_prefix_returns_false(self):
        """Returns False when signature lacks sha256= prefix."""
        result = verify_github_signature(b"payload", "md5=abc", "secret")
        self.assertFalse(result)

    def test_exception_returns_false(self):
        """Returns False when an exception occurs during verification."""
        with patch("webhooks.routes.github.hmac") as mock_hmac:
            mock_hmac.new.side_effect = TypeError("bad type")
            result = verify_github_signature(b"payload", "sha256=abc", "secret")
            self.assertFalse(result)


class TestGetInternalClient(unittest.TestCase):
    """Tests for get_internal_client()."""

    def test_with_socket(self):
        """Returns client with UDS transport when socket is configured."""
        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_with_url(self):
        """Returns client with base_url when URL is configured."""
        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = ""
            mock_settings.github_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)
            self.assertEqual(str(client.base_url), "http://internal:8000")

    def test_socket_takes_priority_over_url(self):
        """Socket transport is used when both socket and URL are configured."""
        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_no_socket_no_url_raises(self):
        """Raises ValueError when neither socket nor URL is configured."""
        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = ""
            mock_settings.github_internal_api_url = ""
            with self.assertRaises(ValueError):
                get_internal_client()


class TestGithubWebhook(unittest.IsolatedAsyncioTestCase):
    """Tests for github_webhook() endpoint."""

    def _make_request(self, body=b'{"action": "push"}', headers=None):
        """Helper to create a mock request."""
        mock_request = AsyncMock()
        mock_request.body.return_value = body
        mock_request.headers = headers or {}
        return mock_request

    async def test_not_configured_returns_503(self):
        """Returns 503 when neither socket nor URL is configured."""
        mock_request = AsyncMock()

        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = ""
            mock_settings.github_internal_api_url = ""
            response = await github_webhook(mock_request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.body, b"Service unavailable")

    async def test_empty_body_returns_200(self):
        """Returns 200 on empty body."""
        request = self._make_request(b"")

        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 200)

    async def test_success_returns_internal_response(self):
        """Returns internal API status code and content on success."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b'{"ok": true}')

    async def test_invalid_signature_returns_401(self):
        """Returns 401 when signature verification fails."""
        request = self._make_request(
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "push",
            }
        )

        with patch("webhooks.routes.github.settings") as mock_settings:
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = "real-secret"
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.body, b"Invalid signature")

    async def test_no_secret_skips_verification(self):
        """Skips signature verification when no secret is configured."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
            patch("webhooks.routes.github.verify_github_signature") as mock_verify,
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 200)
            mock_verify.assert_not_called()

    async def test_valid_signature_with_secret(self):
        """Forwards when signature is valid and secret is configured."""
        secret = "my-secret"
        payload = b'{"action": "push"}'
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        request = self._make_request(
            payload,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "push",
            },
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = secret
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 200)

    async def test_forwards_github_headers(self):
        """Forwards GitHub-specific headers to internal API."""
        request = self._make_request(
            headers={
                "X-Hub-Signature-256": "sha256=abc",
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "delivery-123",
            }
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            await github_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertEqual(headers["X-Hub-Signature-256"], "sha256=abc")
            self.assertEqual(headers["X-GitHub-Event"], "push")
            self.assertEqual(headers["X-GitHub-Delivery"], "delivery-123")

    async def test_missing_github_headers_not_forwarded(self):
        """Only forwards GitHub headers that are present."""
        request = self._make_request(headers={})

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            await github_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertEqual(headers, {"Content-Type": "application/json"})

    async def test_forwards_correct_path_and_body(self):
        """Verifies correct path and body are forwarded."""
        payload = b'{"action": "push", "ref": "refs/heads/main"}'
        request = self._make_request(payload)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            await github_webhook(request)
            call_args = mock_client.post.call_args
            self.assertEqual(call_args[0][0], "/webhooks/github")
            self.assertEqual(call_args[1]["content"], payload)

    async def test_connect_error_returns_502(self):
        """Returns 502 when internal API connection fails."""
        request = self._make_request()

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.body, b"Bad gateway")

    async def test_general_exception_returns_500(self):
        """Returns 500 on unexpected exception."""
        request = self._make_request()

        mock_client = AsyncMock()
        mock_client.post.side_effect = RuntimeError("Unexpected error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.body, b"Internal server error")

    async def test_internal_error_status_forwarded(self):
        """Returns internal API error status code as-is."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.content = b"Unprocessable entity"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""
            response = await github_webhook(request)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.body, b"Unprocessable entity")

    async def test_forwards_authorization_header_with_token(self):
        """Forwards Authorization header when token is configured."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = "gh-token"

            await github_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer gh-token")

    async def test_no_authorization_header_without_token(self):
        """Does not send Authorization header when token is empty."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.github.settings") as mock_settings,
            patch("webhooks.routes.github.get_internal_client", return_value=mock_client),
        ):
            mock_settings.github_internal_api_socket = "/tmp/github.sock"
            mock_settings.github_internal_api_url = ""
            mock_settings.github_webhook_secret = ""
            mock_settings.github_internal_api_token = ""

            await github_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertNotIn("Authorization", call_kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
