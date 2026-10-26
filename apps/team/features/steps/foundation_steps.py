# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the foundation feature: health, CORS, settings, credentials and logging."""

import contextlib
import io
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when


@then("the health version is the package version")
def step_health_version(context) -> None:
    from team import __version__

    assert context.response.json()["version"] == __version__


@when('a browser at the origin "{origin}" requests "{path}"')
def step_request_origin(context, origin: str, path: str) -> None:
    context.response = context.get_client().get(path, headers={"Origin": origin})


@then('the response header "{name}" is "{value}"')
def step_header(context, name: str, value: str) -> None:
    assert context.response.headers.get(name) == value, dict(context.response.headers)


@given('the environment variable "{name}" is "{value}"')
def step_env(context, name: str, value: str) -> None:
    context.environ[name] = value


@when("the settings are loaded")
def step_load_settings(context) -> None:
    from team.config import Settings

    with patch.dict(os.environ, context.environ):
        context.settings = Settings(_env_file=None)


@then('the setting "{name}" is "{value}"')
def step_setting(context, name: str, value: str) -> None:
    assert str(getattr(context.settings, name)) == value, getattr(context.settings, name)


@then('the setting "{name}" contains "{value}"')
def step_setting_contains(context, name: str, value: str) -> None:
    assert value in str(getattr(context.settings, name))


@given('a credentials directory with "{name}" set to "{value}"')
def step_credentials(context, name: str, value: str) -> None:
    directory = tempfile.TemporaryDirectory()
    context.add_cleanup(directory.cleanup)
    (Path(directory.name) / name).write_text(value + "\n")
    context.environ["CREDENTIALS_DIRECTORY"] = directory.name


@when('the credential "{name}" is read')
def step_read_credential(context, name: str) -> None:
    from team.config import get_credential

    with patch.dict(os.environ, context.environ):
        context.credential = get_credential(name, "default")


@then('the credential value is "{value}"')
def step_credential_value(context, value: str) -> None:
    assert context.credential == value, context.credential


@given('logging is set up at level "{level}"')
def step_setup_logging(context, level: str) -> None:
    from team.logging import setup_logging

    context.streams = (io.StringIO(), io.StringIO())
    with (
        contextlib.redirect_stdout(context.streams[0]),
        contextlib.redirect_stderr(context.streams[1]),
    ):
        setup_logging(level)


@given('the request context is user "{user}" and client "{client}"')
def step_request_context(context, user: str, client: str) -> None:
    from team.logging import clear_request_context, set_request_context

    set_request_context(user_id=user, client_id=client)
    context.add_cleanup(clear_request_context)


@when('the application logs "{info}" at level INFO and "{error}" at level ERROR')
def step_log(context, info: str, error: str) -> None:
    logger = logging.getLogger("team.behave")
    logger.info(info)
    logger.error(error)


@then('stdout contains "{wanted}" and not "{unwanted}"')
def step_stdout_split(context, wanted: str, unwanted: str) -> None:
    out = context.streams[0].getvalue()
    assert wanted in out and unwanted not in out, out


@then('stderr contains "{wanted}" and not "{unwanted}"')
def step_stderr_split(context, wanted: str, unwanted: str) -> None:
    err = context.streams[1].getvalue()
    assert wanted in err and unwanted not in err, err


@then('stdout contains "{text}"')
def step_stdout_contains(context, text: str) -> None:
    assert text in context.streams[0].getvalue(), context.streams[0].getvalue()
