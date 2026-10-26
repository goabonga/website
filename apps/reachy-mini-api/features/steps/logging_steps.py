# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the logging feature."""

import io
import logging
import sys

from behave import given, then, when
from reachy_mini_api.logging import get_logger, setup_logging


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
    get_logger("reachy_mini_api.behave").log(getattr(logging, level), message)


@then('stdout should contain "{text}"')
def step_stdout_contains(context, text):
    """Check that stdout holds the text."""
    assert text in context.out.getvalue(), f"stdout: {context.out.getvalue()!r}"


@then('stdout should not contain "{text}"')
def step_stdout_not_contains(context, text):
    """Check that stdout does not hold the text."""
    assert text not in context.out.getvalue(), f"stdout: {context.out.getvalue()!r}"


@then('stderr should contain "{text}"')
def step_stderr_contains(context, text):
    """Check that stderr holds the text."""
    assert text in context.err.getvalue(), f"stderr: {context.err.getvalue()!r}"


@then('stderr should not contain "{text}"')
def step_stderr_not_contains(context, text):
    """Check that stderr does not hold the text."""
    assert text not in context.err.getvalue(), f"stderr: {context.err.getvalue()!r}"
