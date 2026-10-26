# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for foundation.feature."""

import importlib
import io
import logging
import os

import asterisk.config as config_module
from behave import given, then, when

MANAGED_VARIABLES = ("AUDIOSOCKET_HOST", "AUDIOSOCKET_PORT", "LOG_LEVEL")


def _reset_environment(context):
    if not hasattr(context, "saved_environment"):
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
    importlib.reload(config_module)


@given("no AudioSocket or logging variable is set")
def step_no_variables(context):
    _reset_environment(context)


@given('the environment variable "{name}" is "{value}"')
def step_set_variable(context, name, value):
    _reset_environment(context)
    os.environ[name] = value


@given("the configuration is loaded")
@when("the configuration is loaded")
def step_load_configuration(context):
    context.config_module = importlib.reload(config_module)


@then('the AudioSocket address should be "{address}"')
def step_check_address(context, address):
    cfg = context.config_module.Config
    assert f"{cfg.AUDIOSOCKET_HOST}:{cfg.AUDIOSOCKET_PORT}" == address


@then('the log level should be "{level}"')
def step_check_level(context, level):
    assert level == context.config_module.Config.LOG_LEVEL


@given("logging is configured on a clean root logger")
def step_configure_logging(context):
    import asterisk.main as main_module

    root = logging.getLogger()
    context.saved_handlers = list(root.handlers)
    context.saved_level = root.level
    root.handlers.clear()
    context.add_cleanup(_restore_logging, context)
    main_module.setup_logging()


def _restore_logging(context):
    root = logging.getLogger()
    root.handlers[:] = context.saved_handlers
    root.setLevel(context.saved_level)


@when("an INFO record and an ERROR record are emitted")
def step_emit_records(context):
    context.stdout, context.stderr = io.StringIO(), io.StringIO()
    root = logging.getLogger()
    # Handlers bind sys.stdout/sys.stderr at creation; point them at buffers.
    out, err = root.handlers
    out.setStream(context.stdout)
    err.setStream(context.stderr)
    logger = logging.getLogger("asterisk.behave")
    logger.info("info-record")
    logger.error("error-record")


@then("the INFO record should go to stdout only")
def step_info_on_stdout(context):
    assert "info-record" in context.stdout.getvalue()
    assert "info-record" not in context.stderr.getvalue()


@then("the ERROR record should go to stderr only")
def step_error_on_stderr(context):
    assert "error-record" in context.stderr.getvalue()
    assert "error-record" not in context.stdout.getvalue()


@when("the configuration is logged")
def step_log_configuration(context):
    import asterisk.main as main_module

    main_module = importlib.reload(main_module)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        main_module.log_configuration()
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    context.log_text = stream.getvalue()


@then('the log should mention "{text}"')
def step_log_mentions(context, text):
    assert text in context.log_text
