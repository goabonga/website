# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Serve an ASGI application on a real socket, for the duration of a ``with`` block."""

from __future__ import annotations

import socket
import threading
from types import TracebackType
from typing import Any

import uvicorn

#: Seconds to wait for the server to accept connections before giving up.
DEFAULT_STARTUP_TIMEOUT = 10.0
#: Seconds to wait for the server thread to exit once a shutdown is requested.
DEFAULT_SHUTDOWN_TIMEOUT = 10.0


class LiveServerError(RuntimeError):
    """The server could not be started or did not stop in time."""


class LiveServer:
    """Run an ASGI application with uvicorn in a background thread.

    The socket is bound before the thread starts, so ``port=0`` picks a free port
    without any race and :attr:`url` is exact as soon as the server is started.

    If the application has a ``bind_url(url)`` method, it is called with the public
    URL once the socket is bound (the fake OpenID provider uses it to learn its issuer).

    The ASGI lifespan protocol is required (Starlette and FastAPI provide it): a failing
    startup hook then aborts :meth:`start` instead of being silently ignored.
    """

    def __init__(
        self,
        app: Any,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
        shutdown_timeout: float = DEFAULT_SHUTDOWN_TIMEOUT,
        log_level: str = "warning",
    ) -> None:
        self.app = app
        self.host = host
        self._requested_port = port
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout
        self.log_level = log_level
        self._socket: socket.socket | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    @property
    def port(self) -> int:
        """The port the server listens on (available once started)."""
        if self._socket is None:
            return self._requested_port
        return int(self._socket.getsockname()[1])

    @property
    def url(self) -> str:
        """Base URL of the server, without a trailing slash."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> LiveServer:
        """Bind the socket, start the server thread and wait until it is ready."""
        if self._thread is not None:
            raise LiveServerError("the server is already started")
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self._requested_port))
        except OSError as exc:
            sock.close()
            raise LiveServerError(f"cannot bind {self.host}:{self._requested_port}: {exc}") from exc
        self._socket = sock
        self._error = None

        bind_url = getattr(self.app, "bind_url", None)
        if callable(bind_url):
            bind_url(self.url)

        config = uvicorn.Config(self.app, log_level=self.log_level, lifespan="on")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, name="e2e-live-server", daemon=True)
        self._thread.start()

        if not self._wait_until_ready():
            self.stop()
            reason = f": {self._error!r}" if self._error else ""
            raise LiveServerError(
                f"the server did not become ready within {self.startup_timeout}s{reason}"
            )
        return self

    def stop(self) -> None:
        """Ask the server to exit, join its thread and release the socket."""
        server, thread, sock = self._server, self._thread, self._socket
        self._server = self._thread = self._socket = None
        if server is not None:
            server.should_exit = True
        try:
            if thread is not None:
                thread.join(self.shutdown_timeout)
                if thread.is_alive():
                    raise LiveServerError(
                        f"the server did not stop within {self.shutdown_timeout}s"
                    )
        finally:
            if sock is not None:
                sock.close()

    def __enter__(self) -> LiveServer:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def _run(self) -> None:
        assert self._server is not None and self._socket is not None
        try:
            self._server.run(sockets=[self._socket])
        except BaseException as exc:
            self._error = exc

    def _wait_until_ready(self) -> bool:
        server, thread = self._server, self._thread
        assert server is not None and thread is not None
        deadline = threading.Event()
        elapsed, step = 0.0, 0.01
        while elapsed < self.startup_timeout:
            if server.started:
                return True
            if not thread.is_alive():
                return False
            deadline.wait(step)
            elapsed += step
        return False
