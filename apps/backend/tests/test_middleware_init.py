# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.middleware.__init__ lazy imports."""

import pytest


class TestMiddlewareInit:
    """Tests for backend.middleware lazy attribute loading."""

    def test_accessing_rate_limiter_returns_class(self):
        """Accessing RateLimiter via backend.middleware returns the class."""
        import backend.middleware

        result = backend.middleware.RateLimiter
        from backend.middleware.rate_limit import RateLimiter

        assert result is RateLimiter

    def test_accessing_get_rate_limiter_returns_function(self):
        """Accessing get_rate_limiter via backend.middleware returns the function."""
        import backend.middleware

        result = backend.middleware.get_rate_limiter
        from backend.middleware.rate_limit import get_rate_limiter

        assert result is get_rate_limiter

    def test_accessing_check_rate_limit_returns_function(self):
        """Accessing check_rate_limit via backend.middleware returns the function."""
        import backend.middleware

        result = backend.middleware.check_rate_limit
        from backend.middleware.dependencies import check_rate_limit

        assert result is check_rate_limit

    def test_accessing_check_rate_limit_with_context_returns_function(self):
        """Accessing check_rate_limit_with_context via backend.middleware returns the function."""
        import backend.middleware

        result = backend.middleware.check_rate_limit_with_context
        from backend.middleware.dependencies import check_rate_limit_with_context

        assert result is check_rate_limit_with_context

    def test_accessing_unknown_attribute_raises_attribute_error(self):
        """Accessing an unknown attribute via backend.middleware raises AttributeError."""
        import backend.middleware

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = backend.middleware.nonexistent_attribute
