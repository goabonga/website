# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave hooks: every scenario gets its own in-process application.

Scenarios tagged ``@browser`` also run in a real browser against an application
served on a socket (see ``browser_support``); the hooks of ``e2e_support`` start
the browser for them and leave the other scenarios alone.
"""

import sys
from pathlib import Path

from e2e_support import behave_hooks as e2e
from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.main import create_app

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser_support  # noqa: E402


def before_scenario(context, scenario) -> None:
    context.overrides = {}
    context.response = None
    context.analytics_transport = None
    context._client = None
    context.servers = []
    # The application of a browser scenario is started by its steps, once its settings are known
    e2e.before_scenario(context, scenario)
    browser_support.keep_to_the_stack(context, scenario)


def after_scenario(context, scenario) -> None:
    e2e.after_scenario(context, scenario)
    browser_support.stop_servers(context)
    stop_app(context)


def get_client(context) -> TestClient:
    """Start (once per scenario) an application built from the scenario settings.

    The client is used as a context manager, so the application lifespan runs:
    stopping the application flushes the pending analytics events.
    """
    if context._client is None:
        settings = Settings(_env_file=None, **context.overrides)
        client = TestClient(create_app(settings, context.analytics_transport))
        client.__enter__()
        context._client = client
    return context._client


def stop_app(context) -> None:
    """Stop the application of the scenario, if it is running."""
    if context._client is not None:
        client, context._client = context._client, None
        client.__exit__(None, None, None)


def before_all(context) -> None:
    e2e.before_all(context)
    context.get_client = lambda: get_client(context)
    context.stop_app = lambda: stop_app(context)


def after_all(context) -> None:
    e2e.after_all(context)
    browser_support.remove_client_build()
