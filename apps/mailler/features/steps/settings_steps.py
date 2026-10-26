# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions overriding application settings for one scenario."""

from behave import given
from mailler.config import settings


def set_setting(context, name, value):
    """Override a setting; the environment restores it after the scenario."""
    context.settings_backup.setdefault(name, getattr(settings, name))
    setattr(settings, name, value)


@given('the setting "{name}" is "{value}"')
def step_setting_string(context, name, value):
    set_setting(context, name, value)


@given('the setting "{name}" is empty')
def step_setting_empty(context, name):
    set_setting(context, name, "")


@given('the setting "{name}" is {value:d}')
def step_setting_int(context, name, value):
    set_setting(context, name, value)


@given('the setting "{name}" is enabled')
def step_setting_enabled(context, name):
    set_setting(context, name, True)


@given('the setting "{name}" is disabled')
def step_setting_disabled(context, name):
    set_setting(context, name, False)
