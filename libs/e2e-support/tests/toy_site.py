# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A tiny ASGI site shared by the pytest fixtures and the behave project."""


async def site(scope, receive, send):
    """HTML pages that set and echo a cookie, and misbehave on demand."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    path = scope["path"]
    headers = [(b"content-type", b"text/html; charset=utf-8")]
    if path == "/set-cookie":
        headers.append((b"set-cookie", b"visited=yes; Path=/"))
    cookie = dict(scope["headers"]).get(b"cookie", b"").decode()
    body = f"<title>Page {path}</title><h1>Hello {path}</h1><p id='cookie'>{cookie}</p>"
    if path == "/console":
        body += "<script>console.log('fine'); console.error('boom from console')</script>"
    if path == "/crash":
        body += "<script>setTimeout(() => { throw new Error('kaput') }, 0)</script>"
    await send({"type": "http.response.start", "status": 200, "headers": headers})
    await send({"type": "http.response.body", "body": body.encode()})
