# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the client credentials used to call the platform services."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from knowledge.services import service_auth
from knowledge.services.service_auth import (
    ClientCredentials,
    ServiceAuthError,
    TokenCache,
    credentials_for,
    token_url,
)

CREDENTIALS = ClientCredentials(client_id="the-client", client_secret="the-secret")


def _settings(**overrides):
    settings = MagicMock()
    settings.oauth2_issuer = "https://auth.test/"
    settings.oauth2_client_id = "default-client"
    settings.oauth2_client_secret = "default-secret"
    settings.billing_client_id = ""
    settings.billing_client_secret = ""
    settings.service_timeout = 5.0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _response(status=200, body=None):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body if body is not None else {"access_token": "tok"}
    return response


class TestCredentialsFor:
    def test_service_client_wins(self):
        settings = _settings(billing_client_id="billing-client", billing_client_secret="s3")
        with patch.object(service_auth, "get_settings", return_value=settings):
            assert credentials_for("billing") == ClientCredentials("billing-client", "s3")

    def test_falls_back_to_the_application_client(self):
        with patch.object(service_auth, "get_settings", return_value=_settings()):
            assert credentials_for("billing") == ClientCredentials(
                "default-client", "default-secret"
            )

    def test_service_without_settings_uses_the_application_client(self):
        settings = _settings(spec=None)
        del settings.mailler_client_id
        del settings.mailler_client_secret
        with patch.object(service_auth, "get_settings", return_value=settings):
            assert credentials_for("mailler").client_id == "default-client"


class TestTokenUrl:
    def test_token_endpoint_of_the_issuer(self):
        with patch.object(service_auth, "get_settings", return_value=_settings()):
            assert token_url() == "https://auth.test/oauth2/token"

    def test_issuer_is_required(self):
        with patch.object(service_auth, "get_settings", return_value=_settings(oauth2_issuer="")):
            with pytest.raises(ServiceAuthError, match="OAUTH2_ISSUER"):
                token_url()


class TestTokenCacheSync:
    def _get(self, cache, response=None, error=None, scope="svc:scope", credentials=CREDENTIALS):
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = False
        client.post = MagicMock(side_effect=error, return_value=response or _response())
        with (
            patch.object(service_auth, "get_settings", return_value=_settings()),
            patch.object(service_auth.httpx, "Client", return_value=client),
        ):
            return cache.get(credentials, scope), client

    def test_requests_a_token_with_the_client_credentials_grant(self):
        token, client = self._get(TokenCache())
        assert token == "tok"
        client.post.assert_called_once_with(
            "https://auth.test/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "the-client",
                "client_secret": "the-secret",
                "scope": "svc:scope",
            },
        )

    def test_token_is_cached_until_it_expires(self):
        cache = TokenCache()
        self._get(cache)
        token, client = self._get(cache, response=_response(body={"access_token": "other"}))
        assert token == "tok"
        client.post.assert_not_called()

    def test_each_scope_has_its_own_token(self):
        cache = TokenCache()
        self._get(cache, scope="a")
        token, client = self._get(cache, response=_response(body={"access_token": "b"}), scope="b")
        assert token == "b"
        client.post.assert_called_once()

    def test_clear_forgets_the_tokens(self):
        cache = TokenCache()
        self._get(cache)
        cache.clear()
        token, client = self._get(cache, response=_response(body={"access_token": "again"}))
        assert token == "again"
        client.post.assert_called_once()

    def test_expired_token_is_renewed(self):
        cache = TokenCache()
        self._get(cache, response=_response(body={"access_token": "short", "expires_in": 1}))
        token, _ = self._get(cache, response=_response(body={"access_token": "fresh"}))
        assert token == "fresh"

    def test_missing_credentials(self):
        with pytest.raises(ServiceAuthError, match="not configured") as error:
            self._get(TokenCache(), credentials=ClientCredentials("", ""))
        assert error.value.retryable is False

    def test_refused_request_will_not_work_again(self):
        with pytest.raises(ServiceAuthError, match="401") as error:
            self._get(TokenCache(), response=_response(status=401))
        assert error.value.retryable is False

    def test_server_error_can_pass(self):
        with pytest.raises(ServiceAuthError, match="503") as error:
            self._get(TokenCache(), response=_response(status=503))
        assert error.value.retryable is True

    def test_network_error_can_pass(self):
        with pytest.raises(ServiceAuthError, match="token request failed") as error:
            self._get(TokenCache(), error=httpx.ConnectError("down"))
        assert error.value.retryable is True

    def test_response_without_token(self):
        with pytest.raises(ServiceAuthError, match="not valid"):
            self._get(TokenCache(), response=_response(body={"nope": 1}))


class TestTokenCacheAsync:
    async def _aget(self, cache, response=None, error=None, scope="svc:scope"):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(side_effect=error, return_value=response or _response())
        with (
            patch.object(service_auth, "get_settings", return_value=_settings()),
            patch.object(service_auth.httpx, "AsyncClient", return_value=client),
        ):
            return await cache.aget(CREDENTIALS, scope), client

    async def test_requests_and_caches_a_token(self):
        cache = TokenCache()
        token, client = await self._aget(cache)
        assert token == "tok"
        client.post.assert_awaited_once()
        token, client = await self._aget(cache)
        assert token == "tok"
        client.post.assert_not_called()

    async def test_refused_request(self):
        with pytest.raises(ServiceAuthError, match="403"):
            await self._aget(TokenCache(), response=_response(status=403))

    async def test_network_error(self):
        with pytest.raises(ServiceAuthError, match="token request failed"):
            await self._aget(TokenCache(), error=httpx.ConnectError("down"))
