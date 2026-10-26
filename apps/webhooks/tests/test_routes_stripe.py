# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for Stripe webhook proxy."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from webhooks.routes.stripe import get_internal_client, stripe_webhook


class TestGetBillingClient(unittest.TestCase):
    """Tests for get_internal_client()."""

    def test_with_socket(self):
        """Returns client with UDS transport when socket is configured."""
        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_with_url(self):
        """Returns client with base_url when URL is configured."""
        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = ""
            mock_settings.stripe_internal_api_url = "http://billing:8002"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)
            self.assertEqual(str(client.base_url), "http://billing:8002")

    def test_socket_takes_priority_over_url(self):
        """Socket transport is used when both socket and URL are configured."""
        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_url = "http://billing:8002"
            client = get_internal_client()
            self.assertIsInstance(client, httpx.AsyncClient)

    def test_no_socket_no_url_raises(self):
        """Raises ValueError when neither socket nor URL is configured."""
        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = ""
            mock_settings.stripe_internal_api_url = ""
            with self.assertRaises(ValueError):
                get_internal_client()


class TestStripeWebhook(unittest.IsolatedAsyncioTestCase):
    """Tests for stripe_webhook() endpoint."""

    async def test_no_billing_config_returns_503(self):
        """Returns 503 when neither billing socket nor URL is configured."""
        mock_request = AsyncMock()

        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = ""
            mock_settings.stripe_internal_api_url = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.body, b"Service unavailable")

    async def test_empty_body_returns_200(self):
        """Returns 200 on empty body without calling internal API."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b""
        mock_request.headers = {}

        with patch("webhooks.routes.stripe.settings") as mock_settings:
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_url = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 200)

    async def test_success_returns_billing_response(self):
        """Returns billing API status code and content on success."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_123"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"received": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_url = ""
            mock_settings.stripe_internal_api_token = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b'{"received": true}')

    async def test_success_with_url_only(self):
        """Works when only stripe_internal_api_url is configured (no socket)."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_url"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"received": true}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = ""
            mock_settings.stripe_internal_api_url = "http://billing:8002"
            mock_settings.stripe_internal_api_token = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 200)

    async def test_forwards_correct_headers_and_body(self):
        """Verifies correct path, body, and headers are forwarded."""
        mock_request = AsyncMock()
        payload = b'{"type": "invoice.paid"}'
        mock_request.body.return_value = payload
        mock_request.headers = {"Stripe-Signature": "t=999,v1=xyz"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""
            await stripe_webhook(mock_request)
            mock_client.post.assert_called_once_with(
                "/webhooks/stripe",
                content=payload,
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "t=999,v1=xyz",
                },
                timeout=30.0,
            )

    async def test_missing_stripe_signature_header(self):
        """Forwards empty Stripe-Signature when header is missing."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_456"}'
        mock_request.headers = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""
            await stripe_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Stripe-Signature"], "")

    async def test_connect_error_returns_502(self):
        """Returns 502 when billing API connection fails."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_789"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.body, b"Bad gateway")

    async def test_general_exception_returns_500(self):
        """Returns 500 on unexpected exception."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_000"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = RuntimeError("Unexpected error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.body, b"Internal server error")

    async def test_billing_returns_error_status(self):
        """Returns billing API error status code as-is."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_err"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b"Bad request from billing"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""
            response = await stripe_webhook(mock_request)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.body, b"Bad request from billing")

    async def test_forwards_authorization_header_with_token(self):
        """Forwards Authorization header when token is configured."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_token"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = "stripe-token"

            await stripe_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer stripe-token")

    async def test_no_authorization_header_without_token(self):
        """Does not send Authorization header when token is empty."""
        mock_request = AsyncMock()
        mock_request.body.return_value = b'{"id": "evt_notoken"}'
        mock_request.headers = {"Stripe-Signature": "t=123,v1=abc"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"ok"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("webhooks.routes.stripe.settings") as mock_settings,
            patch("webhooks.routes.stripe.get_internal_client", return_value=mock_client),
        ):
            mock_settings.stripe_internal_api_socket = "/tmp/billing.sock"
            mock_settings.stripe_internal_api_token = ""

            await stripe_webhook(mock_request)
            call_kwargs = mock_client.post.call_args[1]
            self.assertNotIn("Authorization", call_kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
