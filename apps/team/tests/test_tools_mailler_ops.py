# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler operations tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, base_url="http://mailler.internal", token="tok-mailler"):
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    ctx = {
        "tool_service": service,
        "agent_config": {
            "credentials": {
                "mailler_base_url": base_url,
                "mailler_token": token,
            },
        },
    }
    return ctx, mock_client


def _json_response(status_code, data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data if data is not None else {}
    resp.text = text
    return resp


# --- mailler_send_email ---


class TestMaillerSendEmail:
    async def test_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(201, {"message_id": "msg_1"}))
        result = await ToolService._registry["mailler_send_email"][0](
            {"to_email": "a@b.com", "subject": "Hi", "html_content": "<p>Hello</p>"}, ctx
        )
        assert result["message_id"] == "msg_1"
        call_url = client.post.call_args[0][0]
        assert "/api/v1/send" in call_url
        payload = client.post.call_args[1]["json"]
        assert payload["to_email"] == "a@b.com"

    async def test_with_optional_fields(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(200, {"message_id": "msg_2"}))
        await ToolService._registry["mailler_send_email"][0](
            {
                "to_email": "a@b.com",
                "subject": "Hi",
                "html_content": "<p>Hi</p>",
                "text_content": "Hi",
                "from_email": "no-reply@goabonga.com",
                "provider": "brevo",
            },
            ctx,
        )
        payload = client.post.call_args[1]["json"]
        assert payload["text_content"] == "Hi"
        assert payload["from_email"] == "no-reply@goabonga.com"
        assert payload["provider"] == "brevo"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(422, text="Bad Request"))
        result = await ToolService._registry["mailler_send_email"][0](
            {"to_email": "a@b.com", "subject": "Hi", "html_content": "<p>Hi</p>"}, ctx
        )
        assert "error" in result
        assert "422" in result["error"]

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["mailler_send_email"][0](
            {"to_email": "a@b.com", "subject": "Hi", "html_content": "<p>Hi</p>"}, ctx
        )
        assert "not configured" in result["error"]

    async def test_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_json_response(201, {"message_id": "msg_3"}))
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.mailler_ops.get_settings") as m:
            m.return_value.mailler_base_url = "http://global-mailler:8000"
            m.return_value.oauth2_client_secret = "global-secret"
            result = await ToolService._registry["mailler_send_email"][0](
                {"to_email": "a@b.com", "subject": "Hi", "html_content": "<p>Hi</p>"}, ctx
            )
        assert result["message_id"] == "msg_3"

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/mailler/mailler.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.post = AsyncMock(return_value=_json_response(201, {"message_id": "m"}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["mailler_send_email"][0](
                {"to_email": "a@b.com", "subject": "Hi", "html_content": "<p>Hi</p>"}, ctx
            )
        assert result["message_id"] == "m"
        mock_uds_client.aclose.assert_awaited_once()


# --- mailler_get_stats ---


class TestMaillerGetStats:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {"sent": 100, "delivered": 95}))
        result = await ToolService._registry["mailler_get_stats"][0]({}, ctx)
        assert result["sent"] == 100

    async def test_with_filters(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["mailler_get_stats"][0](
            {"start_date": "2026-01-01", "end_date": "2026-01-31", "provider": "ses"}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["start_date"] == "2026-01-01"
        assert call_params["provider"] == "ses"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["mailler_get_stats"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["mailler_get_stats"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/mailler/mailler.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"sent": 1}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["mailler_get_stats"][0]({}, ctx)
        assert result["sent"] == 1
        mock_uds_client.aclose.assert_awaited_once()


# --- mailler_list_templates ---


class TestMaillerListTemplates:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {"templates": [{"id": "t1"}]}))
        result = await ToolService._registry["mailler_list_templates"][0]({}, ctx)
        assert "templates" in result

    async def test_with_filters(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["mailler_list_templates"][0](
            {"page": 2, "page_size": 10, "status": "active", "search": "welcome"}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["page"] == 2
        assert call_params["search"] == "welcome"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["mailler_list_templates"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["mailler_list_templates"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/mailler/mailler.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"templates": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["mailler_list_templates"][0]({}, ctx)
        assert "templates" in result
        mock_uds_client.aclose.assert_awaited_once()


# --- mailler_start_campaign ---


class TestMaillerStartCampaign:
    async def test_success(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(200, {"status": "sending"}))
        result = await ToolService._registry["mailler_start_campaign"][0](
            {"campaign_id": "camp_1"}, ctx
        )
        assert result["status"] == "sending"
        call_url = client.post.call_args[0][0]
        assert "/campaigns/camp_1/send" in call_url

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.post = AsyncMock(return_value=_json_response(404, text="Not Found"))
        result = await ToolService._registry["mailler_start_campaign"][0](
            {"campaign_id": "missing"}, ctx
        )
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["mailler_start_campaign"][0](
            {"campaign_id": "camp_1"}, ctx
        )
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/mailler/mailler.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.post = AsyncMock(
                return_value=_json_response(200, {"status": "sending"})
            )
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["mailler_start_campaign"][0](
                {"campaign_id": "camp_1"}, ctx
            )
        assert result["status"] == "sending"
        mock_uds_client.aclose.assert_awaited_once()
