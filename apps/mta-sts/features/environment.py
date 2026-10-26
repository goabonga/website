# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment configuration for BDD tests (in-process, no infrastructure)."""

import asyncio
import sys

from mta_sts.logging import setup_logging
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


def after_scenario(context, scenario):
    """Restore the standard streams replaced by logging scenarios."""
    saved = getattr(context, "saved_streams", None)
    if saved:
        sys.stdout, sys.stderr = saved
        context.saved_streams = None
        setup_logging()
