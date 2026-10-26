# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the logging feature."""

import io
import logging
import sys

from behave import given, then, when
from webhooks.logging import get_logger, setup_logging
from webhooks.main import lifespan


@given('logging is configured at level "{level}"')
def step_configure_logging(context, level):
    """Configure logging with captured stdout and stderr streams."""
    context.out = io.StringIO()
    context.err = io.StringIO()
    context.saved_streams = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = context.out, context.err
    setup_logging(level=level)


@when('the application logs an "{level}" message "{message}"')
def step_log_message(context, level, message):
    """Emit a record through an application logger."""
    get_logger("webhooks.behave").log(getattr(logging, level), message)


@when("the application starts and stops")
def step_run_lifespan(context):
    """Run the application lifespan (the ASGI transport does not)."""

    async def run():
        # lifespan() reconfigures logging, which binds handlers to the current
        # streams: point them at the captured ones first.
        sys.stdout, sys.stderr = context.out, context.err
        async with lifespan(context.app):
            pass

    context.loop.run_until_complete(run())


@then('stdout should contain "{text}"')
def step_stdout_contains(context, text):
    assert text in context.out.getvalue(), f"stdout: {context.out.getvalue()!r}"


@then('stdout should not contain "{text}"')
def step_stdout_not_contains(context, text):
    assert text not in context.out.getvalue(), f"stdout: {context.out.getvalue()!r}"


@then('stderr should contain "{text}"')
def step_stderr_contains(context, text):
    assert text in context.err.getvalue(), f"stderr: {context.err.getvalue()!r}"


@then('stderr should not contain "{text}"')
def step_stderr_not_contains(context, text):
    assert text not in context.err.getvalue(), f"stderr: {context.err.getvalue()!r}"
