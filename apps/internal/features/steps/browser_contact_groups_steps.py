# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the contact groups."""

from behave import then


@then("the mailler service should not have updated the group")
def step_no_group_updated(context):
    context.mock_mailler_groups.update_contact_group.assert_not_awaited()
