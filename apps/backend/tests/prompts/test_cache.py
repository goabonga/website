# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.prompts.cache.PromptCache."""

from unittest.mock import AsyncMock, patch

import pytest
from backend.prompts.cache import DEFAULT_KEY, SCOPE_PREFIX, SLUG_PREFIX, PromptCache


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the PromptCache singleton before and after each test."""
    PromptCache._instance = None
    PromptCache._redis = None
    yield
    PromptCache._instance = None
    PromptCache._redis = None


@pytest.fixture
def mock_redis():
    """Return a mocked async Redis client."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.scan_iter = AsyncMock()
    r.close = AsyncMock()
    return r


@pytest.fixture
def cache(mock_redis):
    """Create a PromptCache instance with mocked Redis."""
    with patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis):
        c = PromptCache()
        yield c


class TestScopeKey:
    """Tests for _scope_key."""

    def test_with_none_scopes_returns_anonymous_key(self, cache):
        """_scope_key(None) should return the anonymous key."""
        key = cache._scope_key(None)
        assert key == f"{SCOPE_PREFIX}__anonymous__"

    def test_with_empty_set_returns_anonymous_key(self, cache):
        """_scope_key(set()) should return the anonymous key."""
        key = cache._scope_key(set())
        assert key == f"{SCOPE_PREFIX}__anonymous__"

    def test_with_scopes_sorts_them(self, cache):
        """_scope_key() should sort scopes for consistent key generation."""
        key = cache._scope_key({"zebra", "alpha", "middle"})
        assert key == f"{SCOPE_PREFIX}alpha:middle:zebra"


class TestGetBySlug:
    """Tests for get_by_slug."""

    async def test_cache_hit(self, cache, mock_redis):
        """get_by_slug() should return cached content on cache hit."""
        mock_redis.get.return_value = "cached prompt content"

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_by_slug("test-slug")

        assert result == "cached prompt content"
        mock_redis.get.assert_awaited_once_with(f"{SLUG_PREFIX}test-slug")

    async def test_cache_miss(self, cache, mock_redis):
        """get_by_slug() should return None on cache miss."""
        mock_redis.get.return_value = None

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_by_slug("missing-slug")

        assert result is None


class TestSetBySlug:
    """Tests for set_by_slug."""

    async def test_set_with_ttl(self, cache, mock_redis):
        """set_by_slug() should use setex when TTL is configured."""
        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_by_slug("test-slug", "prompt content")

        mock_redis.setex.assert_awaited_once_with(f"{SLUG_PREFIX}test-slug", 300, "prompt content")

    async def test_set_without_ttl(self, cache, mock_redis):
        """set_by_slug() should use set when TTL is None."""
        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=None),
        ):
            await cache.set_by_slug("test-slug", "prompt content")

        mock_redis.set.assert_awaited_once_with(f"{SLUG_PREFIX}test-slug", "prompt content")


class TestGetForScopes:
    """Tests for get_for_scopes."""

    async def test_cache_hit(self, cache, mock_redis):
        """get_for_scopes() should return cached content on cache hit."""
        scopes = {"openid", "profile"}
        expected_key = cache._scope_key(scopes)
        mock_redis.get.return_value = "scoped prompt content"

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_for_scopes(scopes)

        assert result == "scoped prompt content"
        mock_redis.get.assert_awaited_once_with(expected_key)


class TestGetForScopesMiss:
    """Tests for get_for_scopes cache miss."""

    async def test_cache_miss(self, cache, mock_redis):
        """get_for_scopes() should return None on cache miss."""
        mock_redis.get.return_value = None

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_for_scopes({"openid"})

        assert result is None


class TestGetDefaultMiss:
    """Tests for get_default cache miss."""

    async def test_cache_miss(self, cache, mock_redis):
        """get_default() should return None on cache miss."""
        mock_redis.get.return_value = None

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_default()

        assert result is None


class TestSetForScopes:
    """Tests for set_for_scopes."""

    async def test_stores_content(self, cache, mock_redis):
        """set_for_scopes() should store content with the correct scope key."""
        scopes = {"openid", "profile"}
        expected_key = cache._scope_key(scopes)

        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_for_scopes(scopes, "scoped content")

        mock_redis.setex.assert_awaited_once_with(expected_key, 300, "scoped content")


class TestGetDefault:
    """Tests for get_default."""

    async def test_cache_hit(self, cache, mock_redis):
        """get_default() should return cached default prompt content."""
        mock_redis.get.return_value = "default prompt content"

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await cache.get_default()

        assert result == "default prompt content"
        mock_redis.get.assert_awaited_once_with(DEFAULT_KEY)


class TestSetDefault:
    """Tests for set_default."""

    async def test_stores_content(self, cache, mock_redis):
        """set_default() should store the default prompt content."""
        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_default("default content")

        mock_redis.setex.assert_awaited_once_with(DEFAULT_KEY, 300, "default content")


class TestInvalidate:
    """Tests for invalidate."""

    async def test_invalidate_all_clears_everything(self, cache, mock_redis):
        """invalidate() without slug should clear all prompt cache keys."""

        async def scan_iter_side_effect(pattern):
            if SLUG_PREFIX in pattern:
                for key in [f"{SLUG_PREFIX}slug1", f"{SLUG_PREFIX}slug2"]:
                    yield key
            elif SCOPE_PREFIX in pattern:
                for key in [f"{SCOPE_PREFIX}scope1"]:
                    yield key

        mock_redis.scan_iter = scan_iter_side_effect

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await cache.invalidate()

        # Should have deleted slug keys, scope keys, and the default key
        assert mock_redis.delete.await_count >= 3
        mock_redis.delete.assert_any_await(DEFAULT_KEY)

    async def test_invalidate_specific_slug(self, cache, mock_redis):
        """invalidate(slug) should clear only that slug and all scope caches."""

        async def scan_iter_side_effect(pattern):
            if SCOPE_PREFIX in pattern:
                for key in [f"{SCOPE_PREFIX}scope1"]:
                    yield key
            else:
                return
                yield  # make it an async generator

        mock_redis.scan_iter = scan_iter_side_effect

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await cache.invalidate(slug="my-slug")

        mock_redis.delete.assert_any_await(f"{SLUG_PREFIX}my-slug")


class TestSingletonPattern:
    """Tests for PromptCache singleton behavior."""

    def test_singleton_pattern(self):
        """Two PromptCache() calls return the same instance."""
        a = PromptCache()
        b = PromptCache()
        assert a is b


class TestGetRedis:
    """Tests for PromptCache.get_redis class method."""

    async def test_get_redis_creates_connection(self):
        """get_redis() should create a new Redis connection via redis.from_url."""
        with patch("backend.prompts.cache.redis") as mock_redis_module:
            fake_redis = AsyncMock()
            mock_redis_module.from_url.return_value = fake_redis
            with patch("backend.prompts.cache.settings") as mock_settings:
                mock_settings.prompt_cache_redis_url = "redis://localhost:6379/0"

                result = await PromptCache.get_redis()

            mock_redis_module.from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                decode_responses=True,
            )
            assert result is fake_redis

    async def test_get_redis_reuses_existing_connection(self):
        """get_redis() should return existing connection without creating a new one."""
        existing_redis = AsyncMock()
        PromptCache._redis = existing_redis

        result = await PromptCache.get_redis()

        assert result is existing_redis


class TestCloseRedis:
    """Tests for PromptCache.close class method."""

    async def test_close_redis(self):
        """close() should close the Redis connection and reset _redis to None."""
        fake_redis = AsyncMock()
        PromptCache._redis = fake_redis

        await PromptCache.close()

        fake_redis.close.assert_awaited_once()
        assert PromptCache._redis is None

    async def test_close_when_no_redis(self):
        """close() should do nothing when _redis is None."""
        PromptCache._redis = None

        await PromptCache.close()

        assert PromptCache._redis is None


class TestGetTtl:
    """Tests for PromptCache._get_ttl."""

    def test_get_ttl_zero_returns_none(self, cache):
        """_get_ttl() should return None when prompt_cache_ttl is 0."""
        with patch("backend.prompts.cache.settings") as mock_settings:
            mock_settings.prompt_cache_ttl = 0
            result = cache._get_ttl()
        assert result is None

    def test_get_ttl_negative_returns_none(self, cache):
        """_get_ttl() should return None when prompt_cache_ttl is negative."""
        with patch("backend.prompts.cache.settings") as mock_settings:
            mock_settings.prompt_cache_ttl = -1
            result = cache._get_ttl()
        assert result is None

    def test_get_ttl_positive_returns_ttl(self, cache):
        """_get_ttl() should return the TTL value when prompt_cache_ttl is positive."""
        with patch("backend.prompts.cache.settings") as mock_settings:
            mock_settings.prompt_cache_ttl = 600
            result = cache._get_ttl()
        assert result == 600


class TestSetBySlugNoTtl:
    """Tests for set_by_slug without TTL."""

    async def test_set_by_slug_no_ttl(self, cache, mock_redis):
        """set_by_slug() should use set (not setex) when _get_ttl returns None."""
        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=None),
        ):
            await cache.set_by_slug("slug-no-ttl", "content")

        mock_redis.set.assert_awaited_once_with(f"{SLUG_PREFIX}slug-no-ttl", "content")
        mock_redis.setex.assert_not_awaited()


class TestRedisErrors:
    """Tests for Redis error handling across all methods."""

    async def test_get_by_slug_redis_error(self, cache):
        """get_by_slug() should catch RedisError and return None."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.get.side_effect = RedisError("Connection refused")

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
        ):
            result = await cache.get_by_slug("test-slug")

        assert result is None

    async def test_set_by_slug_redis_error(self, cache):
        """set_by_slug() should catch RedisError silently."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.setex.side_effect = RedisError("Connection refused")

        with (
            patch.object(
                PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
            ),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_by_slug("test-slug", "content")

        # Should not raise

    async def test_get_for_scopes_redis_error(self, cache):
        """get_for_scopes() should catch RedisError and return None."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.get.side_effect = RedisError("Connection refused")

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
        ):
            result = await cache.get_for_scopes({"openid"})

        assert result is None

    async def test_set_for_scopes_redis_error(self, cache):
        """set_for_scopes() should catch RedisError silently."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.setex.side_effect = RedisError("Connection refused")

        with (
            patch.object(
                PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
            ),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_for_scopes({"openid"}, "content")

        # Should not raise

    async def test_set_for_scopes_no_ttl(self, cache, mock_redis):
        """set_for_scopes() should use set (not setex) when _get_ttl returns None."""
        scopes = {"openid", "profile"}
        expected_key = cache._scope_key(scopes)

        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=None),
        ):
            await cache.set_for_scopes(scopes, "scoped content")

        mock_redis.set.assert_awaited_once_with(expected_key, "scoped content")
        mock_redis.setex.assert_not_awaited()

    async def test_get_default_redis_error(self, cache):
        """get_default() should catch RedisError and return None."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.get.side_effect = RedisError("Connection refused")

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
        ):
            result = await cache.get_default()

        assert result is None

    async def test_set_default_redis_error(self, cache):
        """set_default() should catch RedisError silently."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.setex.side_effect = RedisError("Connection refused")

        with (
            patch.object(
                PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
            ),
            patch.object(cache, "_get_ttl", return_value=300),
        ):
            await cache.set_default("default content")

        # Should not raise

    async def test_set_default_no_ttl(self, cache, mock_redis):
        """set_default() should use set (not setex) when _get_ttl returns None."""
        with (
            patch.object(PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch.object(cache, "_get_ttl", return_value=None),
        ):
            await cache.set_default("default content")

        mock_redis.set.assert_awaited_once_with(DEFAULT_KEY, "default content")
        mock_redis.setex.assert_not_awaited()

    async def test_invalidate_specific_slug(self, cache, mock_redis):
        """invalidate(slug) should delete slug key and clear scope caches."""

        async def scan_iter_side_effect(pattern):
            if SCOPE_PREFIX in pattern:
                for key in [f"{SCOPE_PREFIX}scope1", f"{SCOPE_PREFIX}scope2"]:
                    yield key
            else:
                return
                yield  # make it an async generator

        mock_redis.scan_iter = scan_iter_side_effect

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=mock_redis
        ):
            await cache.invalidate(slug="specific-slug")

        mock_redis.delete.assert_any_await(f"{SLUG_PREFIX}specific-slug")
        mock_redis.delete.assert_any_await(f"{SCOPE_PREFIX}scope1")
        mock_redis.delete.assert_any_await(f"{SCOPE_PREFIX}scope2")

    async def test_invalidate_redis_error(self, cache):
        """invalidate() should catch RedisError silently."""
        from redis.exceptions import RedisError

        failing_redis = AsyncMock()
        failing_redis.delete.side_effect = RedisError("Connection refused")

        with patch.object(
            PromptCache, "get_redis", new_callable=AsyncMock, return_value=failing_redis
        ):
            await cache.invalidate(slug="test-slug")

        # Should not raise

    async def test_clear_calls_invalidate(self, cache):
        """clear() should delegate to invalidate()."""
        with patch.object(cache, "invalidate", new_callable=AsyncMock) as mock_invalidate:
            await cache.clear()

        mock_invalidate.assert_awaited_once_with()
