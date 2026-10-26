# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the security.txt feature."""

from unittest.mock import patch

from behave import given

SECURITY_FIELDS = [
    "security_contact",
    "security_expires",
    "security_encryption",
    "security_acknowledgments",
    "security_preferred_languages",
    "security_canonical",
    "security_policy",
    "security_hiring",
    "security_csaf",
]


@given("the security.txt settings are configured with:")
def step_configure_security_txt(context):
    """Patch the route settings with the values of the table."""
    if "security_txt_settings" in context.patches:
        context.patches["security_txt_settings"].stop()

    patcher = patch("backend.routes.security_txt.settings")
    mock_settings = patcher.start()
    context.patches["security_txt_settings"] = patcher

    for field in SECURITY_FIELDS:
        setattr(mock_settings, field, "")
    for row in context.table:
        setattr(mock_settings, row["field"], row["value"])
