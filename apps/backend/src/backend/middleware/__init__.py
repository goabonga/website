# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Middleware module.

Note: To avoid circular imports, import directly from submodules:
- from backend.middleware.rate_limit import RateLimiter, get_rate_limiter
- from backend.middleware.dependencies import check_rate_limit, check_rate_limit_with_context
"""

# Lazy imports to avoid circular dependency with session.dependencies


def __getattr__(name: str):
    """Lazy attribute loading to avoid circular imports."""
    if name in ("RateLimiter", "get_rate_limiter"):
        from backend.middleware.rate_limit import RateLimiter, get_rate_limiter

        if name == "RateLimiter":
            return RateLimiter
        return get_rate_limiter
    if name in ("check_rate_limit", "check_rate_limit_with_context"):
        from backend.middleware.dependencies import (
            check_rate_limit,
            check_rate_limit_with_context,
        )

        if name == "check_rate_limit":
            return check_rate_limit
        return check_rate_limit_with_context
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RateLimiter",
    "check_rate_limit",
    "check_rate_limit_with_context",
    "get_rate_limiter",
]
