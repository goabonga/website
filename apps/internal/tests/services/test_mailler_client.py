# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Mailler API client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from internal.services.mailler_client import MaillerAPIError, MaillerClient


@pytest.fixture
def client():
    """Create a MaillerClient with mocked settings."""
    with patch("internal.services.mailler_client.settings") as s:
        s.mailler_api_url = "https://mailler.example.com"
        s.mailler_admin_scope = "mailler:admin"
        s.mailler_timeout = 12.5
        s.mailler_socket_path = ""
        s.oauth2_client_id = "test-client"
        s.oauth2_client_secret = "test-secret"
        s.oauth2_issuer = "https://auth.example.com"
        yield MaillerClient()


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


def _no_content_response():
    return httpx.Response(
        204,
        request=httpx.Request("DELETE", "https://mailler.example.com/api/v1/test"),
    )


class TestGetAccessToken:
    @pytest.mark.asyncio
    async def test_fetches_new_token(self, client):
        mock_client = AsyncMock()
        mock_client.post.return_value = _token_response("new-token")

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("mailler:read")
            assert token == "new-token"

    @pytest.mark.asyncio
    async def test_returns_cached_token(self, client):
        client._tokens["mailler:read"] = (
            "cached-token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        token = await client._get_access_token("mailler:read")
        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_refreshes_expired_token(self, client):
        client._tokens["mailler:read"] = (
            "expired-token",
            datetime.now(UTC) - timedelta(hours=1),
        )
        mock_client = AsyncMock()
        mock_client.post.return_value = _token_response("fresh-token")

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await client._get_access_token("mailler:read")
            assert token == "fresh-token"

    @pytest.mark.asyncio
    async def test_raises_when_no_issuer(self):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_api_url = "https://mailler.example.com"
            s.mailler_admin_scope = "mailler:admin"
            s.mailler_timeout = 12.5
            s.mailler_socket_path = ""
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = ""
            c = MaillerClient()
            with pytest.raises(ValueError, match="oauth2_issuer not configured"):
                await c._get_access_token()


class TestRequest:
    @pytest.mark.asyncio
    async def test_returns_empty_when_not_configured(self):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_api_url = ""
            s.mailler_admin_scope = "mailler:admin"
            s.mailler_timeout = 12.5
            s.mailler_socket_path = ""
            s.oauth2_client_id = ""
            s.oauth2_client_secret = ""
            s.oauth2_issuer = ""
            c = MaillerClient()
            result = await c._request("GET", "/test")
            assert result == {}

    @pytest.mark.asyncio
    async def test_request_with_json_response(self, client):
        client._tokens["mailler:read mailler:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_client = AsyncMock()
        mock_client.request.return_value = _json_response({"items": [1, 2]})

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("GET", "/api/v1/test")
            assert result == {"items": [1, 2]}

    @pytest.mark.asyncio
    async def test_request_204_returns_empty(self, client):
        client._tokens["mailler:read mailler:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_client = AsyncMock()
        mock_client.request.return_value = _no_content_response()

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client._request("DELETE", "/api/v1/test")
            assert result == {}


class TestGetContacts:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": "1"}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_contacts()
            assert result == expected

    @pytest.mark.asyncio
    async def test_error_returns_empty(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_contacts()
            assert result["items"] == []
            assert result["total"] == 0


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": "new-id", "email": "test@example.com"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.create_contact({"email": "test@example.com"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error_returns_none(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_contact({"email": "test@example.com"})
            assert result is None


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.delete_contact("contact-id")
            assert result is True

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_contact("contact-id")
            assert result is False


class TestGetTemplates:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": 1}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_templates()
            assert result == expected


class TestSendCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"status": "sending", "task_id": "abc"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.send_campaign(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_http_error_raises_mailler_api_error(self, client):
        error_response = httpx.Response(
            422,
            json={"detail": "Campaign has no recipients"},
            request=httpx.Request("POST", "https://mailler.example.com/api/v1/campaigns/1/send"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "422", request=error_response.request, response=error_response
            ),
        ):
            with pytest.raises(MaillerAPIError) as exc_info:
                await client.send_campaign(1)
            assert "Campaign has no recipients" in str(exc_info.value)
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_error_raises_mailler_api_error(self, client):
        with (
            patch.object(client, "_request", side_effect=ConnectionError("timeout")),
            pytest.raises(MaillerAPIError),
        ):
            await client.send_campaign(1)


class TestDeleteTemplate:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.delete_template(1)
            assert result is True

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_template(1)
            assert result is False


class TestInitSocketPath:
    def test_socket_path_sets_localhost_base_url(self):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_api_url = "https://mailler.example.com"
            s.mailler_admin_scope = "mailler:admin"
            s.mailler_timeout = 12.5
            s.mailler_socket_path = "/run/mailler/mailler.sock"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = MaillerClient()
            assert c._base_url == "http://localhost"
            assert c._socket_path == "/run/mailler/mailler.sock"


class TestRequestSocketTransport:
    @pytest.mark.asyncio
    async def test_uses_socket_transport(self):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_api_url = "https://mailler.example.com"
            s.mailler_admin_scope = "mailler:admin"
            s.mailler_timeout = 12.5
            s.mailler_socket_path = "/run/mailler/mailler.sock"
            s.oauth2_client_id = "test"
            s.oauth2_client_secret = "test"
            s.oauth2_issuer = "https://auth.example.com"
            c = MaillerClient()
            c._tokens["mailler:read mailler:admin"] = (
                "token",
                datetime.now(UTC) + timedelta(hours=1),
            )

            mock_http = AsyncMock()
            mock_http.request.return_value = httpx.Response(
                200,
                json={"ok": True},
                request=httpx.Request("GET", "http://localhost/api/v1/test"),
            )

            with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
                MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await c._request("GET", "/api/v1/test")
                assert result == {"ok": True}
                # Verify transport was passed
                call_kwargs = MockClient.call_args[1]
                assert call_kwargs.get("transport") is not None

    @pytest.mark.asyncio
    async def test_request_propagates_token_error(self, client):
        with (
            patch.object(client, "_get_access_token", side_effect=Exception("token fail")),
            pytest.raises(Exception, match="token fail"),
        ):
            await client._request("GET", "/test")


class TestGetProviders:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(
            client,
            "_request",
            new_callable=AsyncMock,
            return_value={"providers": ["brevo", "ses"]},
        ):
            result = await client.get_providers()
            assert result == ["brevo", "ses"]

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_providers()
            assert result == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_providers()
            assert result == []


class TestGetStats:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"total_sent": 100, "by_provider": {}}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_stats()
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_params(self, client):
        expected = {"total_sent": 50}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_stats(
                start_date="2024-01-01", end_date="2024-01-31", provider="brevo"
            )
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["start_date"] == "2024-01-01"
            assert call_kwargs["params"]["provider"] == "brevo"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_stats()
            assert result == {}

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_stats()
            assert result == {}


class TestGetEmails:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": "1"}], "total": 1, "page": 1, "page_size": 20, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_emails()
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_filters(self, client):
        expected = {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_emails(page=2, page_size=10, provider="ses", status="sent")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["provider"] == "ses"
            assert call_kwargs["params"]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_emails()
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_emails()
            assert result["items"] == []
            assert result["total"] == 0


class TestGetEmail:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": "abc", "status": "sent"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_email("abc")
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_email("abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_email("abc")
            assert result is None


class TestGetTemplate:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "Welcome"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_template(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_template(1)
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_template(1)
            assert result is None


class TestGetTemplatesWithParams:
    @pytest.mark.asyncio
    async def test_with_filters(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_templates(status="active", search="welcome")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["status"] == "active"
            assert call_kwargs["params"]["search"] == "welcome"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_templates()
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_templates()
            assert result["items"] == []


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "New"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.create_template({"name": "New"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_template({"name": "New"})
            assert result is None


class TestUpdateTemplate:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "Updated"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.update_template(1, {"name": "Updated"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_template(1, {"name": "Updated"})
            assert result is None


class TestCompileMjmlClient:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"html": "<p>Hello</p>", "errors": []}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.compile_mjml("<mjml></mjml>")
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.compile_mjml("<mjml></mjml>")
            assert result["html"] == ""
            assert "Compilation failed" in result["errors"]

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.compile_mjml("<mjml></mjml>")
            assert result["html"] == ""
            assert "fail" in result["errors"][0]


class TestRenderTemplateClient:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"html": "<p>Hello John</p>", "subject": "Hi John"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.render_template(1, {"name": "John"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.render_template(1, {"name": "John"})
            assert result is None


class TestGetContact:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": "c1", "email": "test@test.com"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_contact("c1")
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_contact("c1")
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_contact("c1")
            assert result is None


class TestGetContactsWithParams:
    @pytest.mark.asyncio
    async def test_with_filters(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_contacts(status="active", search="john", group_id=5)
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["status"] == "active"
            assert call_kwargs["params"]["search"] == "john"
            assert call_kwargs["params"]["group_id"] == 5


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": "c1", "email": "new@test.com"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.update_contact("c1", {"email": "new@test.com"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_contact("c1", {"email": "new@test.com"})
            assert result is None


class TestUnsubscribeContact:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"status": "unsubscribed"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.unsubscribe_contact("c1")
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.unsubscribe_contact("c1")
            assert result is None


class TestCreateContactsBulk:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"created": 2, "skipped": 0, "failed": 0}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.create_contacts_bulk([{"email": "a@b.com"}, {"email": "c@d.com"}])
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        contacts = [{"email": "a@b.com"}]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.create_contacts_bulk(contacts)
            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_error(self, client):
        contacts = [{"email": "a@b.com"}, {"email": "c@d.com"}]
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_contacts_bulk(contacts)
            assert result["created"] == 0
            assert result["failed"] == 2
            assert "fail" in result["errors"][0]


class TestGetContactGroups:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": 1}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_contact_groups()
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_search(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_contact_groups(search="vip")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["search"] == "vip"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_contact_groups()
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_contact_groups()
            assert result["items"] == []


class TestGetContactGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "VIP"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_contact_group(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_contact_group(1)
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_contact_group(1)
            assert result is None


class TestCreateContactGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "New Group"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.create_contact_group({"name": "New Group"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_contact_group({"name": "New Group"})
            assert result is None


class TestUpdateContactGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "Updated"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.update_contact_group(1, {"name": "Updated"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_contact_group(1, {"name": "Updated"})
            assert result is None


class TestDeleteContactGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.delete_contact_group(1)
            assert result is True

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_contact_group(1)
            assert result is False


class TestGetGroupContacts:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": "c1"}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_group_contacts(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_search(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_group_contacts(1, search="john")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["search"] == "john"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_group_contacts(1)
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_group_contacts(1)
            assert result["items"] == []


class TestGetContactsNotInGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": "c2"}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_contacts_not_in_group(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_search(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_contacts_not_in_group(1, search="jane")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["search"] == "jane"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_contacts_not_in_group(1)
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_contacts_not_in_group(1)
            assert result["items"] == []


class TestAddContactsToGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"added": 2, "skipped": 0}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.add_contacts_to_group(1, ["c1", "c2"])
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.add_contacts_to_group(1, ["c1"])
            assert result["added"] == 0
            assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.add_contacts_to_group(1, ["c1", "c2"])
            assert result["added"] == 0
            assert result["skipped"] == 2


class TestRemoveContactsFromGroup:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"removed": 2, "skipped": 0}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.remove_contacts_from_group(1, ["c1", "c2"])
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.remove_contacts_from_group(1, ["c1"])
            assert result["removed"] == 0
            assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.remove_contacts_from_group(1, ["c1", "c2"])
            assert result["removed"] == 0
            assert result["skipped"] == 2


class TestGetCampaigns:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": 1}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_campaigns()
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_filters(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_campaigns(status="draft", search="welcome")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["status"] == "draft"
            assert call_kwargs["params"]["search"] == "welcome"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_campaigns()
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaigns()
            assert result["items"] == []


class TestGetCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "Welcome"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_campaign(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_campaign(1)
            assert result is None

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaign(1)
            assert result is None


class TestCreateCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "New"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.create_campaign({"name": "New"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.create_campaign({"name": "New"})
            assert result is None


class TestUpdateCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"id": 1, "name": "Updated"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.update_campaign(1, {"name": "Updated"})
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.update_campaign(1, {"name": "Updated"})
            assert result is None


class TestDeleteCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.delete_campaign(1)
            assert result is True

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.delete_campaign(1)
            assert result is False


class TestScheduleCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"status": "scheduled"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.schedule_campaign(1, "2024-12-01T10:00:00Z")
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.schedule_campaign(1, "2024-12-01T10:00:00Z")
            assert result is None


class TestSendCampaignHttpErrorNoJson:
    @pytest.mark.asyncio
    async def test_http_error_without_json_body(self, client):
        error_response = httpx.Response(
            500,
            content=b"Internal Server Error",
            request=httpx.Request("POST", "https://mailler.example.com/api/v1/campaigns/1/send"),
        )
        with patch.object(
            client,
            "_request",
            side_effect=httpx.HTTPStatusError(
                "500", request=error_response.request, response=error_response
            ),
        ):
            with pytest.raises(MaillerAPIError) as exc_info:
                await client.send_campaign(1)
            assert exc_info.value.status_code == 500


class TestPauseCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"status": "paused"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.pause_campaign(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.pause_campaign(1)
            assert result is None


class TestResumeCampaign:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"status": "sending"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.resume_campaign(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.resume_campaign(1)
            assert result is None


class TestGetCampaignPreview:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"html": "<p>Preview</p>"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_campaign_preview(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaign_preview(1)
            assert result is None


class TestGetCampaignSends:
    @pytest.mark.asyncio
    async def test_success(self, client):
        expected = {"items": [{"id": "s1"}], "total": 1, "page": 1, "pages": 1}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=expected):
            result = await client.get_campaign_sends(1)
            assert result == expected

    @pytest.mark.asyncio
    async def test_with_status_filter(self, client):
        expected = {"items": [], "total": 0, "page": 1, "pages": 1}
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=expected
        ) as mock_req:
            result = await client.get_campaign_sends(1, status="delivered")
            assert result == expected
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_campaign_sends(1)
            assert result["items"] == []

    @pytest.mark.asyncio
    async def test_error(self, client):
        with patch.object(client, "_request", side_effect=Exception("fail")):
            result = await client.get_campaign_sends(1)
            assert result["items"] == []


class TestMaillerAPIError:
    def test_attributes(self):
        err = MaillerAPIError("test error", status_code=500)
        assert err.message == "test error"
        assert err.status_code == 500
        assert str(err) == "test error"

    def test_default_status_code(self):
        err = MaillerAPIError("error")
        assert err.status_code == 400


class TestAdminScope:
    def test_the_admin_scope_is_added_to_the_scope_of_the_call(self, client):
        assert client._with_admin("mailler:read") == "mailler:read mailler:admin"
        assert client._with_admin("mailler:stats") == "mailler:stats mailler:admin"

    def test_the_admin_scope_comes_from_the_settings(self, client):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_admin_scope = "mailler:root"
            assert client._with_admin("mailler:write") == "mailler:write mailler:root"

    def test_an_empty_admin_scope_is_left_out(self, client):
        with patch("internal.services.mailler_client.settings") as s:
            s.mailler_admin_scope = ""
            assert client._with_admin("mailler:read") == "mailler:read"

    def test_the_scope_is_not_repeated(self, client):
        assert client._with_admin("mailler:admin") == "mailler:admin"

    @pytest.mark.asyncio
    async def test_the_token_is_requested_with_the_admin_scope(self, client):
        mock_http = AsyncMock()
        mock_http.post.return_value = _token_response("tok")
        mock_http.request.return_value = _json_response({"providers": ["a"]})

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await client.get_providers() == ["a"]

        assert mock_http.post.call_args[1]["data"]["scope"] == "mailler:read mailler:admin"
        assert "mailler:read mailler:admin" in client._tokens

    @pytest.mark.asyncio
    async def test_the_timeout_comes_from_the_settings(self, client):
        client._tokens["mailler:read mailler:admin"] = (
            "token",
            datetime.now(UTC) + timedelta(hours=1),
        )
        mock_http = AsyncMock()
        mock_http.request.return_value = _json_response({})

        with patch("internal.services.mailler_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await client._request("GET", "/api/v1/test")

            assert MockClient.call_args[1]["timeout"] == 12.5
