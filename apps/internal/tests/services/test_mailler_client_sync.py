# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for synchronous Mailler API client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from internal.services.mailler_client_sync import (
    EmailResult,
    SyncMaillerClient,
    get_sync_mailler_client,
)


@pytest.fixture
def client():
    """Create a SyncMaillerClient with mocked settings (no socket)."""
    with patch("internal.services.mailler_client_sync.settings") as s:
        s.mailler_socket_path = ""
        s.mailler_api_url = "https://mailler.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield SyncMaillerClient()


@pytest.fixture
def socket_client():
    """Create a SyncMaillerClient with socket transport."""
    with patch("internal.services.mailler_client_sync.settings") as s:
        s.mailler_socket_path = "/run/mailler/mailler.sock"
        s.mailler_api_url = "https://mailler.example.com"
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield SyncMaillerClient()


def _token_response(token="test-token", expires_in=3600):
    return httpx.Response(
        200,
        json={"access_token": token, "expires_in": expires_in},
        request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
    )


def _json_response(data, status_code=200):
    return httpx.Response(
        status_code,
        json=data,
        request=httpx.Request("GET", "https://mailler.example.com/api/v1/test"),
    )


# =========================================================================
# EmailResult
# =========================================================================


class TestEmailResult:
    def test_success_result(self):
        result = EmailResult(
            success=True,
            email_id="email-123",
            task_id="task-456",
        )
        assert result.success is True
        assert result.email_id == "email-123"
        assert result.task_id == "task-456"
        assert result.error_message is None
        assert result.provider_message_id is None

    def test_failure_result(self):
        result = EmailResult(
            success=False,
            error_message="Something went wrong",
        )
        assert result.success is False
        assert result.error_message == "Something went wrong"
        assert result.email_id is None

    def test_defaults(self):
        result = EmailResult(success=True)
        assert result.error_message is None
        assert result.provider_message_id is None
        assert result.email_id is None
        assert result.task_id is None


# =========================================================================
# __init__
# =========================================================================


class TestInit:
    def test_without_socket(self, client):
        assert client._base_url == "https://mailler.example.com"
        assert client._socket_path == ""

    def test_with_socket(self, socket_client):
        assert socket_client._base_url == "http://localhost"
        assert socket_client._socket_path == "/run/mailler/mailler.sock"

    def test_no_mailler_api_url(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = SyncMaillerClient()
            assert c._base_url == ""

    def test_none_mailler_api_url(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = None
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = SyncMaillerClient()
            assert c._base_url == ""

    def test_trailing_slash_stripped(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = "https://mailler.example.com/"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com/"
            c = SyncMaillerClient()
            assert c._base_url == "https://mailler.example.com"
            assert c._issuer == "https://auth.example.com"


# =========================================================================
# _get_access_token
# =========================================================================


class TestGetAccessToken:
    def test_fetches_new_token(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("mailler:send")
            assert token == "new-token"

    def test_returns_cached_token(self, client):
        client._tokens["mailler:send"] = (
            "cached-token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = client._get_access_token("mailler:send")
        assert token == "cached-token"

    def test_refreshes_expired_token(self, client):
        client._tokens["mailler:send"] = (
            "expired-token",
            datetime.now(UTC) - timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("fresh-token")

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("mailler:send")
            assert token == "fresh-token"

    def test_refreshes_near_expiry_token(self, client):
        client._tokens["mailler:send"] = (
            "near-expiry",
            datetime.now(UTC) + timedelta(seconds=10),
        )
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("new-token")

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("mailler:send")
            assert token == "new-token"

    def test_raises_when_no_issuer(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = "https://mailler.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = SyncMaillerClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                c._get_access_token()

    def test_caches_token_per_scope(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = _token_response("read-token")

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("mailler:read")
            assert token == "read-token"
            assert "mailler:read" in client._tokens

    def test_default_expires_in(self, client):
        mock_http = MagicMock()
        mock_http.post.return_value = httpx.Response(
            200,
            json={"access_token": "tok"},
            request=httpx.Request("POST", "https://auth.example.com/oauth2/token"),
        )

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            token = client._get_access_token("mailler:send")
            assert token == "tok"
            assert "mailler:send" in client._tokens


# =========================================================================
# _request
# =========================================================================


class TestRequest:
    def test_returns_empty_when_not_configured(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = SyncMaillerClient()
            result = c._request("GET", "/test")
            assert result == {}

    def test_success(self, client):
        client._tokens["mailler:send"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = _json_response({"items": [1, 2]})

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = client._request("GET", "/api/v1/test")
            assert result == {"items": [1, 2]}

    def test_propagates_token_error(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            client._request("GET", "/test")

    def test_uses_socket_transport(self, socket_client):
        socket_client._tokens["mailler:send"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", "http://localhost/api/v1/test"),
        )

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = socket_client._request("GET", "/api/v1/test")
            assert result == {"ok": True}
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("transport") is not None

    def test_no_socket_transport(self, client):
        client._tokens["mailler:send"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = _json_response({"ok": True})

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = client._request("GET", "/api/v1/test")
            assert result == {"ok": True}
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs.get("transport") is None

    def test_request_with_params_and_json(self, client):
        client._tokens["mailler:send"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = MagicMock()
        mock_http.request.return_value = _json_response({"ok": True})

        with patch("internal.services.mailler_client_sync.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_http)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = client._request(
                "POST",
                "/api/v1/send",
                params={"key": "val"},
                json_data={"to": "test@test.com"},
                scope="mailler:send",
            )
            assert result == {"ok": True}
            mock_http.request.assert_called_once()


# =========================================================================
# get_providers
# =========================================================================


class TestGetProviders:
    def test_success(self, client):
        with patch.object(
            client,
            "_request",
            return_value={"providers": ["brevo", "ses", "sendgrid"]},
        ):
            result = client.get_providers()
            assert result == ["brevo", "ses", "sendgrid"]

    def test_empty_response(self, client):
        with patch.object(client, "_request", return_value={}):
            result = client.get_providers()
            assert result == []

    def test_falsy_response(self, client):
        with patch.object(client, "_request", return_value=None):
            result = client.get_providers()
            assert result == []

    def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = client.get_providers()
            assert result == []


# =========================================================================
# send_email
# =========================================================================


class TestSendEmail:
    def test_success(self, client):
        with patch.object(
            client,
            "_request",
            return_value={"id": "email-123", "task_id": "task-456"},
        ):
            result = client.send_email(
                to="recipient@example.com",
                subject="Test Subject",
                html_body="<p>Hello</p>",
                plain_body="Hello",
                provider="brevo",
                from_name="Sender",
                from_email="sender@example.com",
                reply_to="reply@example.com",
                metadata={"campaign": "welcome"},
            )
            assert result.success is True
            assert result.email_id == "email-123"
            assert result.task_id == "task-456"

    def test_success_minimal_params(self, client):
        with patch.object(
            client,
            "_request",
            return_value={"id": "email-123"},
        ) as mock_req:
            result = client.send_email(
                to="recipient@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="ses",
            )
            assert result.success is True
            payload = mock_req.call_args[1]["json_data"]
            assert "text_content" not in payload
            assert "from_name" not in payload
            assert "from_email" not in payload
            assert "reply_to" not in payload
            assert "metadata" not in payload

    def test_empty_response(self, client):
        with patch.object(client, "_request", return_value={}):
            result = client.send_email(
                to="recipient@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="ses",
            )
            assert result.success is False
            assert result.error_message == "Empty response from Mailler API"

    def test_http_error_with_json_body(self, client):
        error_response = httpx.Response(
            422,
            json={"detail": "Invalid recipient"},
            request=httpx.Request("POST", "https://mailler.example.com/api/v1/send"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "422", request=error_response.request, response=error_response
            ),
        ):
            result = client.send_email(
                to="bad@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="brevo",
            )
            assert result.success is False
            assert "Invalid recipient" in result.error_message

    def test_http_error_without_json_body(self, client):
        error_response = httpx.Response(
            500,
            content=b"Internal Server Error",
            request=httpx.Request("POST", "https://mailler.example.com/api/v1/send"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            result = client.send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="brevo",
            )
            assert result.success is False
            assert result.error_message is not None

    def test_generic_exception(self, client):
        with patch.object(
            client,
            "_request",
            side_effect=ConnectionError("connection refused"),
        ):
            result = client.send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="brevo",
            )
            assert result.success is False
            assert "connection refused" in result.error_message

    def test_payload_includes_optional_fields(self, client):
        with patch.object(
            client,
            "_request",
            return_value={"id": "email-123"},
        ) as mock_req:
            client.send_email(
                to="recipient@example.com",
                subject="Test",
                html_body="<p>Hello</p>",
                plain_body="Hello",
                provider="brevo",
                from_name="Sender",
                from_email="sender@example.com",
                reply_to="reply@example.com",
                metadata={"key": "val"},
            )
            payload = mock_req.call_args[1]["json_data"]
            assert payload["to_email"] == "recipient@example.com"
            assert payload["subject"] == "Test"
            assert payload["html_content"] == "<p>Hello</p>"
            assert payload["text_content"] == "Hello"
            assert payload["provider"] == "brevo"
            assert payload["from_name"] == "Sender"
            assert payload["from_email"] == "sender@example.com"
            assert payload["reply_to"] == "reply@example.com"
            assert payload["metadata"] == {"key": "val"}

    def test_none_response_from_request(self, client):
        with patch.object(client, "_request", return_value=None):
            result = client.send_email(
                to="test@example.com",
                subject="Test",
                html_body="<p>Hi</p>",
                plain_body=None,
                provider="ses",
            )
            assert result.success is False
            assert result.error_message == "Empty response from Mailler API"


# =========================================================================
# get_sync_mailler_client factory
# =========================================================================


class TestGetSyncMaillerClient:
    def test_returns_instance(self):
        with patch("internal.services.mailler_client_sync.settings") as s:
            s.mailler_socket_path = ""
            s.mailler_api_url = "https://mailler.example.com"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            result = get_sync_mailler_client()
            assert isinstance(result, SyncMaillerClient)
