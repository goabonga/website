# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment for the internal application.

Scenarios run fully in-process, without any external infrastructure:

- the FastAPI application is driven through an ASGI transport;
"""

import asyncio
import contextlib
import os

# Set required env vars BEFORE any internal import
os.environ.setdefault("APP_NAME", "Internal Test")

from internal.main import app


def before_all(context):
    """Set up test infrastructure."""
    context.loop = asyncio.new_event_loop()
    context.app = app
    context._patchers = []


def before_scenario(context, scenario):
    """Reset state before each scenario."""
    # Reset response
    context.response = None
    context.created_ids = []


def after_scenario(context, scenario):
    """Clean up after each scenario."""


def after_all(context):
    """Tear down test infrastructure."""

    for p in getattr(context, "_patchers", []):
        with contextlib.suppress(RuntimeError):
            p.stop()

    if hasattr(context, "loop") and not context.loop.is_closed():
        context.loop.close()

    app.dependency_overrides.clear()
