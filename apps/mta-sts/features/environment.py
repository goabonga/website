# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment configuration for BDD tests (in-process, no infrastructure)."""

import asyncio
import sys

from mta_sts.config import settings
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
    context.setting_backup = {}


def after_scenario(context, scenario):
    """Restore overridden settings and the standard streams."""
    for name, value in context.setting_backup.items():
        setattr(settings, name, value)
    saved = getattr(context, "saved_streams", None)
    if saved:
        sys.stdout, sys.stderr = saved
        context.saved_streams = None
        setup_logging()
