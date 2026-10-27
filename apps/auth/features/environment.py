# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run the FastAPI application in-process through Starlette's
``TestClient``: no network, no PostgreSQL, no Redis and no SMTP server. The
database session dependency is replaced by an ``AsyncMock`` that every
scenario can program.

Scenarios tagged ``@browser`` drive the same application, served on a real
socket in a thread of this interpreter, with a Chromium browser. The mocks and
the SQLite stand-in are patched on the module objects, so the server thread
sees them as the in-process client does.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

from e2e_support import behave_hooks as e2e

# Behave loads this module before the step modules, so the variable is in place
# before ``auth.config`` reads the environment.
UPLOAD_DIR = tempfile.TemporaryDirectory(prefix="auth-behave-")
os.environ.setdefault("UPLOAD_DIRECTORY", UPLOAD_DIR.name)


def _run_outside_the_browser_loop(real_run):
    """Wrap ``asyncio.run`` so that it also works while Playwright's loop is running.

    The synchronous Playwright API keeps an event loop running in the thread that
    executes the steps, where ``asyncio.run`` refuses to start. The steps written for
    the in-process scenarios call it to run a service coroutine: in a browser scenario
    the coroutine is run in a worker thread instead.
    """

    def run(coroutine, **kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return real_run(coroutine, **kwargs)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(real_run, coroutine, **kwargs).result()

    return run


def before_all(context):
    """Import the application once and keep the objects scenarios need."""
    e2e.before_all(context)
    from auth.api.deps import get_db
    from auth.main import app
    from fastapi.testclient import TestClient

    context.app = app
    context.get_db = get_db
    context.client_class = TestClient


def before_scenario(context, scenario):
    """Give every scenario a fresh client and a mocked database session."""
    context.db = AsyncMock()
    context.db.add = MagicMock()

    async def override_get_db():
        yield context.db

    context.app.dependency_overrides[context.get_db] = override_get_db
    context.client = context.client_class(context.app)
    context.response = None
    e2e.before_scenario(
        context, scenario, base_url=lambda: e2e.live_server(context, "auth", context.app).url
    )
    if e2e.is_browser_scenario(scenario):
        patcher = patch.object(asyncio, "run", _run_outside_the_browser_loop(asyncio.run))
        patcher.start()
        context.add_cleanup(patcher.stop)


def after_scenario(context, scenario):
    """Close the browser, the client and remove the dependency overrides."""
    e2e.after_scenario(context, scenario)
    context.client.close()
    context.app.dependency_overrides.clear()


def after_all(context):
    """Stop the browser and the live server, remove the temporary uploads directory."""
    e2e.after_all(context)
    UPLOAD_DIR.cleanup()
