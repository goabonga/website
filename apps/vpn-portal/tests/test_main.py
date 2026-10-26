# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the application wiring in vpn_portal.main."""

from unittest.mock import AsyncMock, patch

from vpn_portal import main


def test_swagger_config_is_empty_without_issuer():
    with patch.object(main, "settings") as settings:
        settings.oauth2_issuer = ""
        settings.oauth2_swagger_client_id = "swagger"

        assert main.get_swagger_ui_oauth2_config() == {}


def test_swagger_config_is_empty_without_client_id():
    with patch.object(main, "settings") as settings:
        settings.oauth2_issuer = "https://auth.example.com"
        settings.oauth2_swagger_client_id = ""

        assert main.get_swagger_ui_oauth2_config() == {}


def test_swagger_config_enables_pkce():
    with patch.object(main, "settings") as settings:
        settings.oauth2_issuer = "https://auth.example.com"
        settings.oauth2_swagger_client_id = "swagger"

        config = main.get_swagger_ui_oauth2_config()

    assert config["swagger_ui_init_oauth"] == {
        "clientId": "swagger",
        "usePkceWithAuthorizationCodeGrant": True,
    }
    assert config["swagger_ui_parameters"] == {"persistAuthorization": True}


async def test_lifespan_closes_the_auth_clients():
    with (
        patch.object(main, "jwks_manager") as jwks,
        patch.object(main, "token_exchange_client") as exchange,
        patch.object(main, "introspection_client") as introspection,
    ):
        for client in (jwks, exchange, introspection):
            client.close = AsyncMock()

        async with main.lifespan(main.app):
            jwks.close.assert_not_called()

        jwks.close.assert_awaited_once()
        exchange.close.assert_awaited_once()
        introspection.close.assert_awaited_once()


def test_openapi_describes_authentication():
    assert "OAuth2" in main.app.description
