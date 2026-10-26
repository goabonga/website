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
    context._client = None
    context.servers = []
    # The application of a browser scenario is started by its steps, once its settings are known
    e2e.before_scenario(context, scenario)
    browser_support.keep_to_the_stack(context, scenario)


def after_scenario(context, scenario) -> None:
    e2e.after_scenario(context, scenario)
    browser_support.stop_servers(context)
    if context._client is not None:
        context._client.close()
        context._client = None


def get_client(context) -> TestClient:
    """Build (once per scenario) a client on an app created from the scenario settings."""
    if context._client is None:
        settings = Settings(_env_file=None, **context.overrides)
        context._client = TestClient(create_app(settings))
    return context._client


def before_all(context) -> None:
    e2e.before_all(context)
    context.get_client = lambda: get_client(context)


def after_all(context) -> None:
    e2e.after_all(context)
    browser_support.remove_client_build()
