# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run entirely in-process: no network, no database, no Redis, no
Step-CA and no OpenVPN server.
"""

import asyncio


def before_scenario(context, scenario):
    """Give every scenario its own event loop, exposed as ``context.run``."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.run = context.loop.run_until_complete
    context.response = None


def after_scenario(context, scenario):
    """Close the scenario event loop."""
    context.loop.close()
