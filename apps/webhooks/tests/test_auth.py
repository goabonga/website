# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhooks.auth module - OAuth2 client_credentials token acquisition."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from webhooks.auth import OAuth2ClientCredentials, get_authorization_header


class TestOAuth2ClientCredentialsIsConfigured(unittest.TestCase):
    """Tests for OAuth2ClientCredentials.is_configured property."""

    def test_configured_when_all_set(self):
        client = OAuth2ClientCredentials()
        with patch("webhooks.auth.settings") as mock_settings:
            mock_settings.oauth2_token_url = "https://auth.example.com/token"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            self.assertTrue(client.is_configured)

    def test_not_configured_when_url_missing(self):
        client = OAuth2ClientCredentials()
        with patch("webhooks.auth.settings") as mock_settings:
            mock_settings.oauth2_token_url = ""
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            self.assertFalse(client.is_configured)

    def test_not_configured_when_client_id_missing(self):
        client = OAuth2ClientCredentials()
        with patch("webhooks.auth.settings") as mock_settings:
            mock_settings.oauth2_token_url = "https://auth.example.com/token"
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = "client-secret"
            self.assertFalse(client.is_configured)

    def test_not_configured_when_secret_missing(self):
        client = OAuth2ClientCredentials()
        with patch("webhooks.auth.settings") as mock_settings:
            mock_settings.oauth2_token_url = "https://auth.example.com/token"
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = ""
            self.assertFalse(client.is_configured)


class TestOAuth2ClientCredentialsGetToken(unittest.IsolatedAsyncioTestCase):
    """Tests for OAuth2ClientCredentials.get_token()."""

    def _configured_settings(self, mock_settings):
        """Set up mock settings as fully configured."""
        mock_settings.oauth2_token_url = "https://auth.example.com/token"
        mock_settings.oauth2_client_id = "client-id"
        mock_settings.oauth2_client_secret = "client-secret"

    async def test_returns_none_when_not_configured(self):
        client = OAuth2ClientCredentials()
        with patch("webhooks.auth.settings") as mock_settings:
            mock_settings.oauth2_token_url = ""
            mock_settings.oauth2_client_id = ""
            mock_settings.oauth2_client_secret = ""
            result = await client.get_token()
            self.assertIsNone(result)

    async def test_returns_cached_token_when_valid(self):
        """Cover lines 43-45: cached token still within TTL."""
        import time

        client = OAuth2ClientCredentials()
        client._token = "cached-token"
        client._expires_at = time.monotonic() + 3600  # Far in the future

        with patch("webhooks.auth.settings") as mock_settings:
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertEqual(result, "cached-token")

    async def test_acquires_new_token_on_success(self):
        """Cover lines 47-77: successful token acquisition."""
        client = OAuth2ClientCredentials()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertEqual(result, "new-token")
            self.assertEqual(client._token, "new-token")

    async def test_acquires_token_with_default_expires_in(self):
        """Cover line 73: uses default 3600 when expires_in missing."""
        client = OAuth2ClientCredentials()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token-no-expiry"}

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertEqual(result, "token-no-expiry")

    async def test_non_200_returns_none_when_no_stale_token(self):
        """Cover lines 60-69: non-200 response, no stale token."""
        client = OAuth2ClientCredentials()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertIsNone(result)

    async def test_non_200_returns_stale_token_when_available(self):
        """Cover lines 66-68: non-200 but stale token still valid."""
        import time

        client = OAuth2ClientCredentials()
        client._token = "stale-token"
        client._expires_at = time.monotonic() + 10  # Still valid but within margin

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertEqual(result, "stale-token")

    async def test_exception_returns_none_when_no_stale_token(self):
        """Cover lines 79-84: exception, no stale token."""
        client = OAuth2ClientCredentials()

        mock_http_client = AsyncMock()
        mock_http_client.post.side_effect = Exception("Connection refused")
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertIsNone(result)

    async def test_exception_returns_stale_token_when_available(self):
        """Cover lines 81-83: exception but stale token still valid."""
        import time

        client = OAuth2ClientCredentials()
        client._token = "stale-token"
        client._expires_at = time.monotonic() + 10

        mock_http_client = AsyncMock()
        mock_http_client.post.side_effect = RuntimeError("Timeout")
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.__aexit__.return_value = None

        with (
            patch("webhooks.auth.settings") as mock_settings,
            patch("webhooks.auth.httpx.AsyncClient", return_value=mock_http_client),
        ):
            self._configured_settings(mock_settings)
            result = await client.get_token()
            self.assertEqual(result, "stale-token")


class TestGetAuthorizationHeader(unittest.IsolatedAsyncioTestCase):
    """Tests for get_authorization_header()."""

    async def test_returns_oauth2_token_when_available(self):
        """Cover line 101: OAuth2 token preferred over static."""
        with patch("webhooks.auth.oauth2_client") as mock_client:
            mock_client.get_token = AsyncMock(return_value="oauth2-token")
            result = await get_authorization_header("static-token")
            self.assertEqual(result, "Bearer oauth2-token")

    async def test_falls_back_to_static_token(self):
        """Cover line 104: falls back to static token when OAuth2 unavailable."""
        with patch("webhooks.auth.oauth2_client") as mock_client:
            mock_client.get_token = AsyncMock(return_value=None)
            result = await get_authorization_header("static-token")
            self.assertEqual(result, "Bearer static-token")

    async def test_returns_none_when_nothing_available(self):
        """Cover line 106: returns None when no tokens available."""
        with patch("webhooks.auth.oauth2_client") as mock_client:
            mock_client.get_token = AsyncMock(return_value=None)
            result = await get_authorization_header("")
            self.assertIsNone(result)

    async def test_returns_none_with_default_static_token(self):
        """Cover line 106: returns None with default empty static token."""
        with patch("webhooks.auth.oauth2_client") as mock_client:
            mock_client.get_token = AsyncMock(return_value=None)
            result = await get_authorization_header()
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
