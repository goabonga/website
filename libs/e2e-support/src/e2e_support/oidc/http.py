# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Small HTTP helpers shared by the endpoints of the fake provider."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

from fastapi import Request


async def read_form(request: Request) -> dict[str, str]:
    """The urlencoded body of a request (python-multipart is not needed)."""
    body = (await request.body()).decode("utf-8", "replace")
    return dict(parse_qsl(body, keep_blank_values=True))


def with_params(url: str, **params: str | None) -> str:
    """``url`` with the non-empty ``params`` appended to its query string."""
    query = urlencode({k: v for k, v in params.items() if v})
    if not query:
        return url
    return f"{url}{'&' if '?' in url else '?'}{query}"
