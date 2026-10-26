# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.mailler — MaillerClient."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from auth.services.mailler import MaillerClient, get_mailler_client


@pytest.fixture
def client():
    return MaillerClient()


# ── __init__ ──────────────────────────────────────────────────────────────────


class TestInit:
    def test_default_state(self, client):
        assert client._access_token is None
        assert client._token_expires_at == 0


# ── _get_http_client ─────────────────────────────────────────────────────────


class TestGetHttpClient:
    def test_tcp_transport(self, client):
        with patch("auth.services.mailler.settings") as mock_settings:
            mock_settings.mailler_unix_socket = None
            with patch("auth.services.mailler.httpx.Client") as MockClient:
                mock_http = MagicMock()
                MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
                MockClient.return_value.__exit__ = MagicMock(return_value=False)
                with client._get_http_client() as c:
                    assert c is mock_http

    def test_unix_socket_transport(self, client):
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.HTTPTransport") as MockTransport,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_unix_socket = "/tmp/mailler.sock"
            mock_http = MagicMock()
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with client._get_http_client() as c:
                assert c is mock_http
            MockTransport.assert_called_once()


# ── _get_access_token ────────────────────────────────────────────────────────


class TestGetAccessToken:
    def test_cached_token(self, client):
        client._access_token = "cached_token"
        client._token_expires_at = time.time() + 3600
        result = client._get_access_token()
        assert result == "cached_token"

    def test_no_auth_url_raises(self, client):
        with patch("auth.services.mailler.settings") as mock_settings:
            mock_settings.mailler_auth_url = None
            mock_settings.issuer = None
            with pytest.raises(ValueError, match="MAILLER_AUTH_URL or ISSUER"):
                client._get_access_token()

    def test_successful_token_acquisition(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
        }

        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_auth_url = "https://auth.example.com"
            mock_settings.mailler_client_id = "client_id"
            mock_settings.mailler_client_secret = "secret"
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            result = client._get_access_token()

        assert result == "new_token"
        assert client._access_token == "new_token"

    def test_failed_token_acquisition(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_auth_url = "https://auth.example.com"
            mock_settings.mailler_client_id = "client_id"
            mock_settings.mailler_client_secret = "secret"
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(Exception, match="Token acquisition failed"):
                client._get_access_token()

    def test_http_request_error(self, client):
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_auth_url = "https://auth.example.com"
            mock_settings.mailler_client_id = "client_id"
            mock_settings.mailler_client_secret = "secret"
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.RequestError("connection failed")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(httpx.RequestError):
                client._get_access_token()

    def test_uses_issuer_fallback(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token",
            "expires_in": 3600,
        }
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_auth_url = None
            mock_settings.issuer = "https://issuer.example.com"
            mock_settings.mailler_client_id = "id"
            mock_settings.mailler_client_secret = "sec"
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            result = client._get_access_token()
        assert result == "token"

    def test_default_expires_in(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "tok"}  # No expires_in

        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch("auth.services.mailler.httpx.Client") as MockClient,
        ):
            mock_settings.mailler_auth_url = "https://auth.example.com"
            mock_settings.mailler_client_id = "id"
            mock_settings.mailler_client_secret = "sec"
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)
            client._get_access_token()
        assert client._token_expires_at > 0


# ── send_email ───────────────────────────────────────────────────────────────


class TestSendEmail:
    def test_no_mailler_url_raises(self, client):
        with patch("auth.services.mailler.settings") as mock_settings:
            mock_settings.mailler_url = None
            with pytest.raises(ValueError, match="MAILLER_URL is not configured"):
                client.send_email("test@example.com", "Subject", "<p>HTML</p>")

    def test_success_minimal(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "email-1"}

        client._get_access_token = MagicMock(return_value="token")
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch.object(client, "_get_http_client") as mock_get_client,
        ):
            mock_settings.mailler_url = "https://mailler.example.com"
            mock_settings.mailler_provider = "ses"
            mock_settings.mailler_unix_socket = None
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)
            result = client.send_email("test@example.com", "Subject", "<p>HTML</p>")

        assert result == {"id": "email-1"}

    def test_success_all_fields(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"id": "email-2"}

        client._get_access_token = MagicMock(return_value="token")
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch.object(client, "_get_http_client") as mock_get_client,
        ):
            mock_settings.mailler_url = "https://mailler.example.com"
            mock_settings.mailler_provider = "ses"
            mock_settings.mailler_unix_socket = "/tmp/sock"
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)
            result = client.send_email(
                "test@example.com",
                "Subject",
                "<p>HTML</p>",
                text_content="Text",
                from_email="from@example.com",
                from_name="Sender",
                to_name="Recipient",
                reply_to="reply@example.com",
                provider="smtp",
                metadata={"key": "value"},
            )
        assert result["id"] == "email-2"

    def test_send_failure(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        client._get_access_token = MagicMock(return_value="token")
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch.object(client, "_get_http_client") as mock_get_client,
        ):
            mock_settings.mailler_url = "https://mailler.example.com"
            mock_settings.mailler_provider = "ses"
            mock_settings.mailler_unix_socket = None
            mock_http = MagicMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(Exception, match="Mailler send failed"):
                client.send_email("test@example.com", "Subject", "<p>HTML</p>")

    def test_http_request_error(self, client):
        client._get_access_token = MagicMock(return_value="token")
        with (
            patch("auth.services.mailler.settings") as mock_settings,
            patch.object(client, "_get_http_client") as mock_get_client,
        ):
            mock_settings.mailler_url = "https://mailler.example.com"
            mock_settings.mailler_provider = "ses"
            mock_settings.mailler_unix_socket = None
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.RequestError("connection error")
            mock_get_client.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_get_client.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(httpx.RequestError):
                client.send_email("test@example.com", "Subject", "<p>HTML</p>")


# ── get_mailler_client ───────────────────────────────────────────────────────


class TestGetMaillerClient:
    def test_singleton(self):
        import auth.services.mailler as mod

        mod._mailler_client = None
        client1 = get_mailler_client()
        client2 = get_mailler_client()
        assert client1 is client2
        mod._mailler_client = None  # Cleanup
