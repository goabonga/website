# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/auth/token_exchange.py — 100% coverage with only mocks."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# =====================================================================
# TokenExchangeError
# =====================================================================


class TestTokenExchangeError:
    def test_is_exception(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        err = TokenExchangeError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"


# =====================================================================
# TokenExchangeClient
# =====================================================================


class TestTokenExchangeClient:
    def _make_client(
        self,
        issuer="https://auth.example.com",
        client_id="cid",
        client_secret="csecret",
        cache_ttl=300,
        redis_url="redis://localhost:6379/0",
    ):
        with patch("knowledge.auth.token_exchange.settings") as ms:
            ms.oauth2_issuer = issuer
            ms.oauth2_client_id = client_id
            ms.oauth2_client_secret = client_secret
            ms.oauth2_token_cache_ttl = cache_ttl
            ms.redis_url = redis_url
            from knowledge.auth.token_exchange import TokenExchangeClient

            c = TokenExchangeClient()
        return c

    # ------------------------------------------------------------------
    # __init__
    # ------------------------------------------------------------------
    def test_init(self):
        c = self._make_client()
        assert c.issuer == "https://auth.example.com"
        assert c.client_id == "cid"
        assert c.client_secret == "csecret"
        assert c.cache_ttl == 300
        assert c._http_client is None
        assert c._redis_client is None

    # ------------------------------------------------------------------
    # get_http_client
    # ------------------------------------------------------------------
    async def test_get_http_client_creates_new(self):
        c = self._make_client()
        with patch("knowledge.auth.token_exchange.httpx.AsyncClient") as mock_ac:
            mock_instance = MagicMock()
            mock_ac.return_value = mock_instance
            client = await c.get_http_client()
        assert client is mock_instance
        mock_ac.assert_called_once_with(timeout=10.0)

    async def test_get_http_client_reuses_open(self):
        c = self._make_client()
        existing = MagicMock()
        existing.is_closed = False
        c._http_client = existing
        client = await c.get_http_client()
        assert client is existing

    async def test_get_http_client_recreates_closed(self):
        c = self._make_client()
        closed = MagicMock()
        closed.is_closed = True
        c._http_client = closed
        with patch("knowledge.auth.token_exchange.httpx.AsyncClient") as mock_ac:
            new = MagicMock()
            mock_ac.return_value = new
            client = await c.get_http_client()
        assert client is new

    # ------------------------------------------------------------------
    # get_redis_client
    # ------------------------------------------------------------------
    async def test_get_redis_client_creates_new(self):
        c = self._make_client()
        with patch("knowledge.auth.token_exchange.redis.from_url") as mock_from_url:
            mock_redis = MagicMock()
            mock_from_url.return_value = mock_redis
            client = await c.get_redis_client()
        assert client is mock_redis
        mock_from_url.assert_called_once()

    async def test_get_redis_client_reuses(self):
        c = self._make_client()
        existing = MagicMock()
        c._redis_client = existing
        client = await c.get_redis_client()
        assert client is existing

    # ------------------------------------------------------------------
    # _cache_key
    # ------------------------------------------------------------------
    def test_cache_key_deterministic(self):
        c = self._make_client()
        key1 = c._cache_key("token1", ["a", "b"])
        key2 = c._cache_key("token1", ["a", "b"])
        assert key1 == key2
        assert key1.startswith("knowledge:token_exchange:")

    def test_cache_key_sorted_scopes(self):
        c = self._make_client()
        key1 = c._cache_key("token1", ["b", "a"])
        key2 = c._cache_key("token1", ["a", "b"])
        assert key1 == key2

    def test_cache_key_different_tokens(self):
        c = self._make_client()
        key1 = c._cache_key("token1", ["a"])
        key2 = c._cache_key("token2", ["a"])
        assert key1 != key2

    # ------------------------------------------------------------------
    # exchange_token
    # ------------------------------------------------------------------
    async def test_exchange_not_configured_no_issuer(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client(issuer="")
        with pytest.raises(TokenExchangeError, match="not configured"):
            await c.exchange_token("tok")

    async def test_exchange_not_configured_no_client_id(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client(client_id="")
        with pytest.raises(TokenExchangeError, match="not configured"):
            await c.exchange_token("tok")

    async def test_exchange_not_configured_no_client_secret(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client(client_secret="")
        with pytest.raises(TokenExchangeError, match="not configured"):
            await c.exchange_token("tok")

    async def test_exchange_cache_hit(self):
        c = self._make_client()
        cached_data = {"access_token": "cached", "scope": "a b"}

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        c._redis_client = mock_redis

        result = await c.exchange_token("tok", requested_scopes=["a", "b"])
        assert result == cached_data

    async def test_exchange_cache_miss_success(self):
        c = self._make_client()

        # Redis cache miss
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        c._redis_client = mock_redis

        # HTTP success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": "a b"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        result = await c.exchange_token("tok", requested_scopes=["a", "b"])
        assert result == {"access_token": "new", "scope": "a b"}
        mock_redis.setex.assert_awaited_once()

    async def test_exchange_no_scopes(self):
        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        c._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": ""}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        result = await c.exchange_token("tok")
        assert result["access_token"] == "new"

    async def test_exchange_http_non_200(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        c._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error_description": "invalid_grant"}'
        mock_response.json.return_value = {"error_description": "invalid_grant"}
        mock_response.text = "Bad Request"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        with pytest.raises(TokenExchangeError, match="Token exchange failed"):
            await c.exchange_token("tok")

    async def test_exchange_http_non_200_no_content(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        c._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b""
        mock_response.json.return_value = {}
        mock_response.text = "Bad Request"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        with pytest.raises(TokenExchangeError, match="Token exchange failed"):
            await c.exchange_token("tok")

    async def test_exchange_http_request_error(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        c._redis_client = mock_redis

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=httpx.RequestError("connection failed", request=MagicMock())
        )
        mock_http.is_closed = False
        c._http_client = mock_http

        with pytest.raises(TokenExchangeError, match="request failed"):
            await c.exchange_token("tok")

    async def test_exchange_redis_error_on_get(self):
        """Redis error on cache get is handled gracefully, proceeds to HTTP."""
        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("redis down"))
        mock_redis.setex = AsyncMock()
        c._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": "a"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        result = await c.exchange_token("tok", requested_scopes=["a"])
        assert result["access_token"] == "new"

    async def test_exchange_redis_error_on_set(self):
        """Redis error on cache set is handled gracefully."""
        c = self._make_client()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock(side_effect=RuntimeError("redis down"))
        c._redis_client = mock_redis

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "scope": "a"}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        c._http_client = mock_http

        result = await c.exchange_token("tok", requested_scopes=["a"])
        assert result["access_token"] == "new"

    # ------------------------------------------------------------------
    # validate_token_scopes
    # ------------------------------------------------------------------
    async def test_validate_scopes_all_granted(self):
        c = self._make_client()
        c.exchange_token = AsyncMock(return_value={"scope": "a b c", "access_token": "tok"})
        result = await c.validate_token_scopes("tok", ["a", "b"])
        assert result["access_token"] == "tok"

    async def test_validate_scopes_missing(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client()
        c.exchange_token = AsyncMock(return_value={"scope": "a", "access_token": "tok"})
        with pytest.raises(TokenExchangeError, match="not granted"):
            await c.validate_token_scopes("tok", ["a", "b"])

    async def test_validate_scopes_empty_scope(self):
        from knowledge.auth.token_exchange import TokenExchangeError

        c = self._make_client()
        c.exchange_token = AsyncMock(return_value={"scope": "", "access_token": "tok"})
        with pytest.raises(TokenExchangeError, match="not granted"):
            await c.validate_token_scopes("tok", ["a"])

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------
    async def test_close_all_open(self):
        c = self._make_client()
        mock_http = AsyncMock()
        mock_http.is_closed = False
        c._http_client = mock_http

        mock_redis = AsyncMock()
        c._redis_client = mock_redis

        await c.close()
        mock_http.aclose.assert_awaited_once()
        mock_redis.aclose.assert_awaited_once()

    async def test_close_http_already_closed(self):
        c = self._make_client()
        mock_http = AsyncMock()
        mock_http.is_closed = True
        c._http_client = mock_http

        mock_redis = AsyncMock()
        c._redis_client = mock_redis

        await c.close()
        mock_http.aclose.assert_not_awaited()
        mock_redis.aclose.assert_awaited_once()

    async def test_close_no_clients(self):
        c = self._make_client()
        c._http_client = None
        c._redis_client = None
        # Should not raise
        await c.close()


# =====================================================================
# Singleton: get_token_exchange_client
# =====================================================================


class TestGetTokenExchangeClient:
    def test_creates_singleton(self):
        import knowledge.auth.token_exchange as te_mod

        te_mod._token_exchange_client = None
        with patch("knowledge.auth.token_exchange.settings") as ms:
            ms.oauth2_issuer = "https://auth.example.com"
            ms.oauth2_client_id = "cid"
            ms.oauth2_client_secret = "csecret"
            ms.oauth2_token_cache_ttl = 300
            ms.redis_url = "redis://localhost:6379/0"
            c1 = te_mod.get_token_exchange_client()
            c2 = te_mod.get_token_exchange_client()
        assert c1 is c2
        te_mod._token_exchange_client = None

    def test_returns_existing(self):
        import knowledge.auth.token_exchange as te_mod

        sentinel = MagicMock()
        te_mod._token_exchange_client = sentinel
        assert te_mod.get_token_exchange_client() is sentinel
        te_mod._token_exchange_client = None
