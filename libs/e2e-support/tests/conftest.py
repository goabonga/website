# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Fixtures of the browser tests; they skip cleanly when no browser can run."""

import pytest
from e2e_support.browser import BrowserSession, BrowserUnavailable
from e2e_support.server import LiveServer
from e2e_support.settings import E2ESettings


async def _site(scope, receive, send):
    """A tiny ASGI site: HTML pages that set and echo a cookie."""
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


@pytest.fixture(scope="session")
def e2e_settings() -> E2ESettings:
    return E2ESettings.from_env()


@pytest.fixture(scope="session")
def browser_session(e2e_settings):
    """One browser for the whole test run; skips the test if none can start."""
    if e2e_settings.skip_browser:
        pytest.skip("E2E_SKIP_BROWSER is set")
    session = BrowserSession(e2e_settings)
    try:
        session.start()
    except BrowserUnavailable as exc:
        pytest.skip(str(exc))
    yield session
    session.stop()


@pytest.fixture(scope="session")
def site():
    """The tiny ASGI site served on a real port."""
    with LiveServer(_site) as server:
        yield server
