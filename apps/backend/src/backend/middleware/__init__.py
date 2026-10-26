# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Middleware module.

Note: To avoid circular imports, import directly from submodules:
- from backend.middleware.rate_limit import RateLimiter, get_rate_limiter
"""

# Lazy imports to avoid circular dependency with session.dependencies


def __getattr__(name: str):
    """Lazy attribute loading to avoid circular imports."""
    if name in ("RateLimiter", "get_rate_limiter"):
        from backend.middleware.rate_limit import RateLimiter, get_rate_limiter

        if name == "RateLimiter":
            return RateLimiter
        return get_rate_limiter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RateLimiter",
    "get_rate_limiter",
]
