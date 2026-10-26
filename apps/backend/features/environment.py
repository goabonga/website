# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run in-process: the FastAPI application is driven through the
Starlette test client, and every external dependency is replaced by a fake
or a patch. No database or Redis server is needed.
"""

from backend.main import app
from starlette.testclient import TestClient


def before_scenario(context, scenario):
    """Create a fresh client and an empty patch registry."""
    context.app = app
    context.patches = {}
    context.client = TestClient(app, raise_server_exceptions=False)


def after_scenario(context, scenario):
    """Undo overrides, stop patches and close the client."""
    context.app.dependency_overrides.clear()
    for patcher in context.patches.values():
        patcher.stop()
    context.patches.clear()
    context.client.close()
