# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the application foundation feature."""

import os

from auth.config import Settings
from auth.core.database import get_async_database_url
from behave import given, then, when

SETTING_VARIABLES = ("LOG_LEVEL", "DATABASE_URL", "DATABASE_POOL_SIZE")


@given("no auth variable is set in the environment")
def step_no_variable(context):
    for name in SETTING_VARIABLES:
        os.environ.pop(name, None)


@given('the environment variable "{name}" is "{value}"')
def step_set_variable(context, name, value):
    previous = os.environ.get(name)
    os.environ[name] = value
    context.add_cleanup(_restore, name, previous)


def _restore(name, previous):
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


@when("the settings are loaded")
def step_load_settings(context):
    context.settings = Settings(_env_file=None)


@when('the async database URL is derived from "{url}"')
def step_derive_url(context, url):
    context.async_url = get_async_database_url(url)


@then('the log level is "{level}"')
def step_log_level(context, level):
    assert context.settings.log_level == level


@then('the database URL is "{url}"')
def step_database_url(context, url):
    assert context.settings.database_url == url


@then("the database pool size is {size:d}")
def step_pool_size(context, size):
    assert context.settings.database_pool_size == size


@then('the async database URL is "{url}"')
def step_async_url(context, url):
    assert context.async_url == url


@then("the database was not queried")
def step_database_untouched(context):
    context.db.execute.assert_not_called()


@then('the application title is "{title}"')
def step_application_title(context, title):
    assert context.settings.app_title == title


@then('the Swagger UI client is "{client_id}" with the scopes "{scopes}"')
def step_swagger_client(context, client_id, scopes):
    assert context.settings.swagger_client_id == client_id
    assert context.settings.swagger_scopes == scopes
