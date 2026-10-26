# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""LiveServer serves an ASGI application on a real socket."""

import socket

import httpx
import pytest
from e2e_support.server import LiveServer, LiveServerError


async def hello(scope, receive, send):
    """Minimal ASGI application answering every HTTP request with a body."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": scope["path"].encode()})


def test_serves_the_application_on_a_random_port():
    with LiveServer(hello) as server:
        assert server.port != 0
        assert server.url == f"http://127.0.0.1:{server.port}"
        response = httpx.get(f"{server.url}/ping")
    assert response.status_code == 200
    assert response.text == "/ping"


def test_two_servers_get_distinct_ports():
    with LiveServer(hello) as first, LiveServer(hello) as second:
        assert first.port != second.port


def test_stop_releases_the_port():
    server = LiveServer(hello).start()
    port = server.port
    server.stop()
    assert not server.is_running
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_stop_is_idempotent():
    server = LiveServer(hello).start()
    server.stop()
    server.stop()


def test_a_requested_port_is_honoured():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    with LiveServer(hello, port=free_port) as server:
        assert server.port == free_port


def test_binding_a_busy_port_fails_with_a_clear_error():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        with pytest.raises(LiveServerError, match="cannot bind"):
            LiveServer(hello, port=busy.getsockname()[1]).start()


def test_starting_twice_is_refused():
    with LiveServer(hello) as server, pytest.raises(LiveServerError, match="already started"):
        server.start()


def test_the_application_learns_its_public_url():
    class Recording:
        url = None

        def bind_url(self, url):
            self.url = url

        async def __call__(self, scope, receive, send):
            await hello(scope, receive, send)

    app = Recording()
    with LiveServer(app) as server:
        assert app.url == server.url


def test_a_failing_startup_is_reported():
    async def broken(scope, receive, send):
        if scope["type"] == "lifespan":
            await receive()
            raise RuntimeError("boom")

    with pytest.raises(LiveServerError):
        LiveServer(broken, startup_timeout=3).start()
