# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks.

Scenarios run entirely in-process: no network, no database, no Asterisk.
"""

import asyncio


def before_scenario(context, scenario):
    """Give every scenario its own event loop, exposed as ``context.run``."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)
    context.run = context.loop.run_until_complete


def after_scenario(context, scenario):
    """Cancel leftover tasks and close the scenario event loop."""
    pending = asyncio.all_tasks(context.loop)
    for task in pending:
        task.cancel()
    if pending:
        context.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    context.loop.close()
