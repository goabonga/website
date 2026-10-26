# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Request utility functions."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies.

    Checks X-Forwarded-For (standard proxy header) and X-Real-IP (nginx)
    before falling back to the direct client address.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"
