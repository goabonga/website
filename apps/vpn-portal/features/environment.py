# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run entirely in-process: no network, no database, no Redis, no
Step-CA and no OpenVPN server.
"""

import asyncio
import os

# The OAuth2 scheme is built when the application is imported.
os.environ.setdefault("OAUTH2_ISSUER", "https://auth.test.example.com")

from vpn_portal.main import app  # noqa: E402


def before_scenario(context, scenario):
    """Give every scenario its own event loop, exposed as ``context.run``."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.run = context.loop.run_until_complete
    context.app = app
    context.headers = {}
    context.response = None


def after_scenario(context, scenario):
    """Close the scenario event loop."""
    context.loop.close()
