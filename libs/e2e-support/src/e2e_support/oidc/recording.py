# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""ASGI middleware recording every request the provider receives."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl

from e2e_support.oidc.models import RecordedRequest


class RecordingMiddleware:
    """Keeps a :class:`RecordedRequest` per HTTP request, in arrival order."""

    def __init__(self, app: Any, sink: list[RecordedRequest]) -> None:
        self.app = app
        self.sink = sink

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_body = bytearray()
        response_body = bytearray()
        status = 0
        recorded = False

        def record() -> None:
            nonlocal recorded
            if recorded:
                return
            recorded = True
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]
            }
            is_form = headers.get("content-type", "").startswith(
                "application/x-www-form-urlencoded"
            )
            self.sink.append(
                RecordedRequest(
                    method=scope["method"],
                    path=scope["path"],
                    query=dict(parse_qsl(scope.get("query_string", b"").decode("latin-1"))),
                    form=dict(parse_qsl(request_body.decode("utf-8", "replace")))
                    if is_form
                    else {},
                    headers=headers,
                    status=status,
                    response_body=bytes(response_body),
                )
            )

        async def recording_receive() -> dict[str, Any]:
            message = await receive()
            request_body.extend(message.get("body", b""))
            return message

        async def recording_send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))
                if not message.get("more_body"):
                    # Record before the client can see the end of the response, so a test
                    # that inspects the requests right after it never misses this one.
                    record()
            await send(message)

        try:
            await self.app(scope, recording_receive, recording_send)
        finally:
            record()
