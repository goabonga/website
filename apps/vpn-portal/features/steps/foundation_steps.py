# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for foundation.feature."""

import io
import logging
import os
import sys

from behave import given, then, when
from vpn_portal.config import Settings
from vpn_portal.logging import get_logger, setup_logging

MANAGED_VARIABLES = ("APP_NAME", "DEBUG", "DOCS_ENABLED", "LOG_LEVEL")


def _isolate_environment(context):
    if hasattr(context, "saved_environment"):
        return
    context.saved_environment = {name: os.environ.get(name) for name in MANAGED_VARIABLES}
    for name in MANAGED_VARIABLES:
        os.environ.pop(name, None)
    context.add_cleanup(_restore_environment, context)


def _restore_environment(context):
    for name, value in context.saved_environment.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@then('the response should contain "{key}" with title "{title}"')
def step_check_title(context, key, title):
    assert context.response.json()[key]["title"] == title


@given("no portal setting is defined in the environment")
def step_no_settings(context):
    _isolate_environment(context)


@given('the environment variable "{name}" is "{value}"')
def step_set_variable(context, name, value):
    _isolate_environment(context)
    os.environ[name] = value


@when("the settings are loaded")
def step_load_settings(context):
    context.settings = Settings(_env_file=None)


@then('the application name should be "{name}"')
def step_check_name(context, name):
    assert context.settings.app_name == name


@then('the log level should be "{level}"')
def step_check_level(context, level):
    assert context.settings.log_level == level


@given("logging is configured on a clean root logger")
def step_configure_logging(context):
    root = logging.getLogger()
    context.saved_handlers = list(root.handlers)
    context.saved_level = root.level
    context.saved_streams = (sys.stdout, sys.stderr)
    context.stdout, context.stderr = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = context.stdout, context.stderr
    context.add_cleanup(_restore_logging, context)
    setup_logging("INFO")


def _restore_logging(context):
    sys.stdout, sys.stderr = context.saved_streams
    root = logging.getLogger()
    root.handlers[:] = context.saved_handlers
    root.setLevel(context.saved_level)


@when("an INFO record and an ERROR record are emitted")
def step_emit_records(context):
    logger = get_logger("features.foundation")
    logger.info("info-marker")
    logger.error("error-marker")


@then("the INFO record should be written to stdout only")
def step_info_stdout(context):
    assert "info-marker" in context.stdout.getvalue()
    assert "info-marker" not in context.stderr.getvalue()


@then("the ERROR record should be written to stderr only")
def step_error_stderr(context):
    assert "error-marker" in context.stderr.getvalue()
    assert "error-marker" not in context.stdout.getvalue()
