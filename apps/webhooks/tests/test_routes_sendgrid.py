# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for SendGrid webhook proxy."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec
from webhooks.routes.sendgrid import (
    get_internal_client,
    sendgrid_webhook,
    verify_sendgrid_signature,
)


class TestVerifySendgridSignature(unittest.TestCase):
    """Tests for verify_sendgrid_signature()."""

    def test_no_signature_returns_false(self):
        """Returns False when signature is missing."""
        result = verify_sendgrid_signature(b"payload", "", "12345", "some-key")
        self.assertFalse(result)

    def test_no_timestamp_returns_false(self):
        """Returns False when timestamp is missing."""
        result = verify_sendgrid_signature(b"payload", "some-sig", "", "some-key")
        self.assertFalse(result)

    def test_no_signature_and_no_timestamp_returns_false(self):
        """Returns False when both signature and timestamp are missing."""
        result = verify_sendgrid_signature(b"payload", "", "", "some-key")
        self.assertFalse(result)

    def test_valid_signature(self):
        """Returns True when signature is valid (mocked crypto)."""
        with (
            patch("webhooks.routes.sendgrid.serialization") as mock_serial,
            patch("webhooks.routes.sendgrid.base64") as mock_b64,
        ):
            mock_key = MagicMock(spec=ec.EllipticCurvePublicKey)
            mock_serial.load_pem_public_key.return_value = mock_key
            mock_b64.b64decode.return_value = b"decoded_sig"

            result = verify_sendgrid_signature(
                b"payload",
                "sig",
                "ts",
                "-----BEGIN PUBLIC KEY-----\nkey\n-----END PUBLIC KEY-----",
            )
            self.assertTrue(result)
            mock_key.verify.assert_called_once()
            call_args = mock_key.verify.call_args
            self.assertEqual(call_args[0][1], b"tspayload")

    def test_non_ecdsa_key_returns_false(self):
        """Returns False when loaded key is not an ECDSA key."""
        with patch("webhooks.routes.sendgrid.serialization") as mock_serial:
            mock_key = MagicMock()  # Not spec'd as EllipticCurvePublicKey
            mock_serial.load_pem_public_key.return_value = mock_key

            result = verify_sendgrid_signature(
                b"payload",
                "sig",
                "ts",
                "-----BEGIN PUBLIC KEY-----\nrsa-key\n-----END PUBLIC KEY-----",
            )
            self.assertFalse(result)

    def test_invalid_signature_returns_false(self):
        """Returns False when crypto raises InvalidSignature."""
        with (
            patch("webhooks.routes.sendgrid.serialization") as mock_serial,
            patch("webhooks.routes.sendgrid.base64") as mock_b64,
        ):
            mock_key = MagicMock(spec=ec.EllipticCurvePublicKey)
            mock_key.verify.side_effect = InvalidSignature()
            mock_serial.load_pem_public_key.return_value = mock_key
            mock_b64.b64decode.return_value = b"decoded_sig"

            result = verify_sendgrid_signature(
                b"payload",
                "sig",
                "ts",
                "-----BEGIN PUBLIC KEY-----\nkey\n-----END PUBLIC KEY-----",
            )
            self.assertFalse(result)

    def test_other_exception_returns_false(self):
        """Returns False on unexpected exception during verification."""
        with patch("webhooks.routes.sendgrid.serialization") as mock_serial:
            mock_serial.load_pem_public_key.side_effect = ValueError("bad key format")

            result = verify_sendgrid_signature(
                b"payload",
                "sig",
                "ts",
                "bad-key",
            )
            self.assertFalse(result)


class TestGetInternalClient(unittest.TestCase):
    """Tests for get_internal_client()."""

    def test_with_socket(self):
        """Returns client with UDS transport when socket is configured."""
        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_with_url(self):
        """Returns client with base_url when URL is configured."""
        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = ""
            mock_settings.sendgrid_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)
            self.assertEqual(str(client.base_url), "http://internal:8000")

    def test_socket_takes_priority_over_url(self):
        """Socket transport is used when both socket and URL are configured."""
        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = "http://internal:8000"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_no_socket_no_url_raises(self):
        """Raises ValueError when neither socket nor URL is configured."""
        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = ""
            mock_settings.sendgrid_internal_api_url = ""
            with self.assertRaises(ValueError):
                get_internal_client()


class TestSendgridWebhook(unittest.IsolatedAsyncioTestCase):
    """Tests for sendgrid_webhook() endpoint."""

    def _make_request(self, body=b'[{"event": "delivered"}]', headers=None):
        """Helper to create a mock request."""
        mock_request = AsyncMock()
        mock_request.body.return_value = body
        mock_request.headers = headers or {}
        return mock_request

    async def test_not_configured_returns_503(self):
        """Returns 503 when neither socket nor URL is configured."""
        mock_request = AsyncMock()

        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = ""
            mock_settings.sendgrid_internal_api_url = ""
            response = await sendgrid_webhook(mock_request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.body, b"Service unavailable")

    async def test_empty_body_returns_200(self):
        """Returns 200 on empty body."""
        request = self._make_request(b"")

        with patch("webhooks.routes.sendgrid.settings") as mock_settings:
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            response = await sendgrid_webhook(request)
            self.assertEqual(response.status_code, 200)

    async def test_success_returns_internal_response(self):
        """Returns internal API status code and content on success."""
        request = self._make_request(
            headers={
                "X-Twilio-Email-Event-Webhook-Signature": "test-sig",
                "X-Twilio-Email-Event-Webhook-Timestamp": "test-ts",
            }
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"ok": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            response = await sendgrid_webhook(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b'{"ok": true}')

    async def test_invalid_signature_returns_401(self):
        """Returns 401 when signature verification fails."""
        request = self._make_request(
            headers={
                "X-Twilio-Email-Event-Webhook-Signature": "bad-sig",
                "X-Twilio-Email-Event-Webhook-Timestamp": "12345",
            }
        )

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.verify_sendgrid_signature", return_value=False),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = "some-key"
            mock_settings.sendgrid_internal_api_token = ""
            response = await sendgrid_webhook(request)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.body, b"Invalid signature")

    async def test_no_key_skips_verification(self):
        """Skips signature verification when no key is configured."""
        request = self._make_request()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
            patch("webhooks.routes.sendgrid.verify_sendgrid_signature") as mock_verify,
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            response = await sendgrid_webhook(request)
            self.assertEqual(response.status_code, 200)
            mock_verify.assert_not_called()

    async def test_forwards_signature_headers(self):
        """Forwards SendGrid signature headers to internal API."""
        request = self._make_request(
            headers={
                "X-Twilio-Email-Event-Webhook-Signature": "test-sig",
                "X-Twilio-Email-Event-Webhook-Timestamp": "test-ts",
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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            await sendgrid_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertEqual(headers["X-Twilio-Email-Event-Webhook-Signature"], "test-sig")
            self.assertEqual(headers["X-Twilio-Email-Event-Webhook-Timestamp"], "test-ts")

    async def test_missing_signature_headers_not_forwarded(self):
        """Does not forward signature headers when they are missing."""
        request = self._make_request(headers={})

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            await sendgrid_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            headers = call_kwargs["headers"]
            self.assertNotIn("X-Twilio-Email-Event-Webhook-Signature", headers)
            self.assertNotIn("X-Twilio-Email-Event-Webhook-Timestamp", headers)

    async def test_forwards_correct_path_and_body(self):
        """Verifies correct path and body are forwarded."""
        payload = b'[{"event": "bounce", "email": "test@example.com"}]'
        request = self._make_request(payload)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            await sendgrid_webhook(request)
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            self.assertEqual(call_args[0][0], "/webhooks/sendgrid")
            self.assertEqual(call_args[1]["content"], payload)

    async def test_connect_error_returns_502(self):
        """Returns 502 when internal API connection fails."""
        request = self._make_request()

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            response = await sendgrid_webhook(request)
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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            response = await sendgrid_webhook(request)
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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            response = await sendgrid_webhook(request)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.body, b"Unprocessable entity")

    async def test_signature_verification_called_with_key(self):
        """Ensures verify is called with correct args when key is configured."""
        payload = b'[{"event": "delivered"}]'
        request = self._make_request(
            payload,
            headers={
                "X-Twilio-Email-Event-Webhook-Signature": "test-sig",
                "X-Twilio-Email-Event-Webhook-Timestamp": "test-ts",
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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
            patch(
                "webhooks.routes.sendgrid.verify_sendgrid_signature", return_value=True
            ) as mock_verify,
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = "my-key"
            mock_settings.sendgrid_internal_api_token = ""

            await sendgrid_webhook(request)
            mock_verify.assert_called_once_with(payload, "test-sig", "test-ts", "my-key")

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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = "sg-token"

            await sendgrid_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer sg-token")

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
            patch("webhooks.routes.sendgrid.settings") as mock_settings,
            patch("webhooks.routes.sendgrid.get_internal_client", return_value=mock_client),
        ):
            mock_settings.sendgrid_internal_api_socket = "/tmp/sendgrid.sock"
            mock_settings.sendgrid_internal_api_url = ""
            mock_settings.sendgrid_webhook_verification_key = ""
            mock_settings.sendgrid_internal_api_token = ""

            await sendgrid_webhook(request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertNotIn("Authorization", call_kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
