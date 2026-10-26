# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps specific to the application foundation feature."""

from behave import then


@then('the JSON field "version" is a semantic version')
def step_version_is_semver(context):
    parts = context.response.json()["version"].split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)
