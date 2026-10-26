# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment configuration for BDD tests (in-process, no infrastructure)."""

import asyncio

from mta_sts.main import app


def before_all(context):
    """Create the event loop and expose the ASGI application."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.app = app


def after_all(context):
    """Close the event loop."""
    context.loop.close()


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
