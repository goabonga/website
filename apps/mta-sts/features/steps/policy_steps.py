# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the policy feature."""

import re

from behave import given, then
from mta_sts.config import settings


@given('the setting "{name}" is "{value}"')
def step_override_setting(context, name, value):
    """Override a setting for the duration of the scenario."""
    context.setting_backup.setdefault(name, getattr(settings, name))
    current = getattr(settings, name)
    setattr(settings, name, type(current)(value))


@then("the policy should have {count:d} lines")
def step_policy_line_count(context, count):
    """Check that the policy has the expected number of lines."""
    lines = context.response.text.strip().split("\n")
    assert len(lines) == count, f"Expected {count} lines, got {len(lines)}: {lines}"


@then('each line should match the pattern "{pattern}"')
def step_each_line_matches_pattern(context, pattern):
    """Check that each line matches a key: value pattern."""
    for line in context.response.text.strip().split("\n"):
        assert re.match(pattern, line), f"Line does not match '{pattern}': {line}"
