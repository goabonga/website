# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the application foundation feature."""

from behave import when


@when('a browser at origin "{origin}" sends a preflight request to "{path}"')
def step_preflight(context, origin, path):
    context.response = context.call(
        "OPTIONS",
        path,
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
