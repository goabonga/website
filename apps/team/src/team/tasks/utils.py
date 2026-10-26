# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Utilities for running async code inside synchronous Celery tasks."""

import asyncio
import threading
from collections.abc import Coroutine
from typing import TypeVar

T = TypeVar("T")

_local = threading.local()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """Return a per-thread event loop, creating one if needed.

    asyncpg connections are bound to the event loop that created them.
    Using a single loop per worker thread avoids "Future attached to a
    different loop" errors when the SQLAlchemy connection pool reuses
    connections across Celery task invocations.
    """
    loop: asyncio.AbstractEventLoop | None = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.loop = loop
    return loop


def run_async(coro: Coroutine[object, object, T]) -> T:
    """Run an async coroutine on the worker's persistent event loop.

    Celery tasks are synchronous, so this bridge is needed to call
    async database and LLM operations from within a task.
    """
    loop = _get_worker_loop()
    return loop.run_until_complete(coro)
