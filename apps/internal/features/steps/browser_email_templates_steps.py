# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the email templates."""

from behave import then


@then('the mailler service should have been asked to create the template "{name}"')
def step_template_created(context, name):
    template = context.mock_mailler_templates.create_template.await_args.args[0]
    assert template["name"] == name, template
    assert "<mjml>" in template["mjml_source"], template


@then("the mailler service should not have been asked to create a template")
def step_no_template_created(context):
    context.mock_mailler_templates.create_template.assert_not_awaited()


@then("the mailler service should not have updated the template")
def step_no_template_updated(context):
    context.mock_mailler_templates.update_template.assert_not_awaited()


@then('the template should have been created with the source containing "{text}"')
def step_template_source(context, text):
    template = context.mock_mailler_templates.create_template.await_args.args[0]
    assert text in template["mjml_source"], template["mjml_source"]
