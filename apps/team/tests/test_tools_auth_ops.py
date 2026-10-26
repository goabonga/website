# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth operations tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import team.services.tools  # noqa: F401
from team.services.tool_service import ToolService


def _mock_context(*, base_url="http://auth.internal", token="tok-auth"):
    service = ToolService()
    mock_client = AsyncMock()
    service._client = mock_client
    ctx = {
        "tool_service": service,
        "agent_config": {
            "credentials": {
                "auth_base_url": base_url,
                "auth_token": token,
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


# --- auth_list_users ---


class TestAuthListUsers:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"users": [{"id": "u1", "email": "a@b.com"}]})
        )
        result = await ToolService._registry["auth_list_users"][0]({}, ctx)
        assert "users" in result
        call_url = client.get.call_args[0][0]
        assert "/admin/api/users" in call_url

    async def test_with_filters(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["auth_list_users"][0](
            {"search": "john", "limit": 10, "offset": 5, "is_active": True}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["search"] == "john"
        assert call_params["limit"] == 10
        assert call_params["offset"] == 5
        assert call_params["is_active"] == "true"

    async def test_is_active_false(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["auth_list_users"][0]({"is_active": False}, ctx)
        call_params = client.get.call_args[1]["params"]
        assert call_params["is_active"] == "false"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(403, text="Forbidden"))
        result = await ToolService._registry["auth_list_users"][0]({}, ctx)
        assert "error" in result
        assert "403" in result["error"]

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["auth_list_users"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_falls_back_to_global_settings(self):
        service = ToolService()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_json_response(200, {"users": []}))
        service._client = mock_client

        ctx = {"tool_service": service, "agent_config": {"credentials": {}}}
        with patch("team.services.tools.auth_ops.get_settings") as m:
            m.return_value.auth_base_url = "http://global-auth:8000"
            m.return_value.oauth2_client_secret = "global-secret"
            result = await ToolService._registry["auth_list_users"][0]({}, ctx)
        assert "users" in result

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/auth/auth.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"users": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["auth_list_users"][0]({}, ctx)
        assert "users" in result
        mock_uds_client.aclose.assert_awaited_once()


# --- auth_list_clients ---


class TestAuthListClients:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {"clients": [{"client_id": "c1"}]}))
        result = await ToolService._registry["auth_list_clients"][0]({}, ctx)
        assert "clients" in result
        call_url = client.get.call_args[0][0]
        assert "/admin/api/clients" in call_url

    async def test_with_filters(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["auth_list_clients"][0](
            {"search": "team", "limit": 5, "offset": 10}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["search"] == "team"
        assert call_params["limit"] == 5

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(500, text="Error"))
        result = await ToolService._registry["auth_list_clients"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["auth_list_clients"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/auth/auth.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"clients": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["auth_list_clients"][0]({}, ctx)
        assert "clients" in result
        mock_uds_client.aclose.assert_awaited_once()


# --- auth_list_roles ---


class TestAuthListRoles:
    async def test_success(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(
            return_value=_json_response(200, {"roles": [{"name": "admin", "scopes": ["*"]}]})
        )
        result = await ToolService._registry["auth_list_roles"][0]({}, ctx)
        assert "roles" in result
        call_url = client.get.call_args[0][0]
        assert "/admin/api/roles" in call_url

    async def test_with_search(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(200, {}))
        await ToolService._registry["auth_list_roles"][0](
            {"search": "admin", "limit": 20, "offset": 5}, ctx
        )
        call_params = client.get.call_args[1]["params"]
        assert call_params["search"] == "admin"

    async def test_api_error(self):
        ctx, client = _mock_context()
        client.get = AsyncMock(return_value=_json_response(403, text="Forbidden"))
        result = await ToolService._registry["auth_list_roles"][0]({}, ctx)
        assert "error" in result

    async def test_no_base_url(self):
        ctx, _ = _mock_context(base_url="")
        result = await ToolService._registry["auth_list_roles"][0]({}, ctx)
        assert "not configured" in result["error"]

    async def test_unix_socket(self):
        ctx, _ = _mock_context(base_url="unix:///run/auth/auth.sock")
        with patch("team.services.tools._http.httpx") as mock_httpx:
            mock_uds_client = AsyncMock()
            mock_uds_client.get = AsyncMock(return_value=_json_response(200, {"roles": []}))
            mock_uds_client.aclose = AsyncMock()
            mock_httpx.AsyncHTTPTransport.return_value = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_uds_client

            result = await ToolService._registry["auth_list_roles"][0]({}, ctx)
        assert "roles" in result
        mock_uds_client.aclose.assert_awaited_once()
