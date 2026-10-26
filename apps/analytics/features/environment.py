# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: scenarios run in-process, without external infrastructure."""

import asyncio


def before_all(context):
    """Create the event loop and load the ASGI application."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)

    from analytics.main import app

    context.app = app


def after_all(context):
    """Close the event loop."""
    context.loop.close()


def before_scenario(context, scenario):
    """Reset the per-scenario response state."""
    context.response = None
    context.response_json = None
