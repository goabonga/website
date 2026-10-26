# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the logging feature."""

import io
import logging
import sys

from behave import given, then, when
from frontend.logging import (
    clear_request_context,
    get_logger,
    set_request_context,
    setup_logging,
)


@given('logging is configured at level "{level}"')
def step_configure_logging(context, level: str) -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, sys.stdout, sys.stderr)

    def restore() -> None:
        root.handlers[:], root.level, sys.stdout, sys.stderr = (
            saved[0],
            saved[1],
            saved[2],
            saved[3],
        )
        clear_request_context()

    context.add_cleanup(restore)
    context.stdout, context.stderr = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = context.stdout, context.stderr
    setup_logging(level)


@given('the request context has user "{user}" and client "{client}"')
def step_request_context(context, user: str, client: str) -> None:
    set_request_context(user_id=user, client_id=client)


@when('an info record "{info}" and a warning record "{warning}" are logged')
def step_log_records(context, info: str, warning: str) -> None:
    logger = get_logger("frontend.behave")
    logger.info(info)
    logger.warning(warning)


@then('standard output contains "{text}"')
def step_stdout_contains(context, text: str) -> None:
    assert text in context.stdout.getvalue(), context.stdout.getvalue()


@then('standard output does not contain "{text}"')
def step_stdout_lacks(context, text: str) -> None:
    assert text not in context.stdout.getvalue(), context.stdout.getvalue()


@then('standard error contains "{text}"')
def step_stderr_contains(context, text: str) -> None:
    assert text in context.stderr.getvalue(), context.stderr.getvalue()


@then('standard error does not contain "{text}"')
def step_stderr_lacks(context, text: str) -> None:
    assert text not in context.stderr.getvalue(), context.stderr.getvalue()
