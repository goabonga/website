# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the nginx rendering feature."""

import os
from unittest.mock import AsyncMock, MagicMock

from behave import given, then, when
from custom_domain.models import CustomDomain, NginxTemplate
from custom_domain.services import nginx_manager, template_service
from custom_domain.services.privileged import sudoers_lines
from environment import start_patch


@given('a domain "{name}" proxied to "{upstream}"')
def step_domain(context, name, upstream):
    context.domain = CustomDomain(
        domain=name,
        client_id="tenant-a",
        owner_id="org_1",
        owner_type="organization",
        upstream_target=upstream,
        cname_target="apps.example.com",
        metadata_={},
    )


@given('a custom HTTP template "{source}"')
def step_custom_template(context, source):
    context.template = NginxTemplate(
        slug="custom", name="Custom", http_template=source, https_template=source
    )


@when("I render the default HTTP configuration")
def step_render_http(context):
    context.rendered = context.loop.run_until_complete(
        nginx_manager.generate_http_config(context.domain)
    )


@when("I render the default HTTPS configuration")
def step_render_https(context):
    context.rendered = context.loop.run_until_complete(
        nginx_manager.generate_https_config(context.domain)
    )


@when("I render the configuration with the custom template")
def step_render_custom(context):
    context.rendered = context.loop.run_until_complete(
        nginx_manager.generate_http_config(context.domain, context.template)
    )


@then('the configuration contains "{text}"')
def step_config_contains(context, text):
    assert text in context.rendered, context.rendered


@then('the configuration does not contain "{text}"')
def step_config_lacks(context, text):
    assert text not in context.rendered, context.rendered


@when('I check the template "{source}"')
def step_validate(context, source):
    context.validation = template_service.validate_template(source.replace("\\n", "\n"))


@when('I render the template "{source}" for domain "{domain}"')
def step_validate_with_domain(context, source, domain):
    context.validation = template_service.validate_template(source, {"domain": domain})


@then("the template is invalid")
def step_template_invalid(context):
    assert not context.validation.valid


@then("the template is valid")
def step_template_valid(context):
    assert context.validation.valid, context.validation.errors


@then('the template error mentions "{text}"')
def step_template_error(context, text):
    assert any(text in error for error in context.validation.errors), context.validation.errors


@then('the rendered template is "{text}"')
def step_rendered(context, text):
    assert context.validation.rendered_output == text


@given("the system commands are recorded instead of executed")
def step_record_commands(context):
    context.commands = []

    async def fake_exec(*cmd, **kwargs):
        context.commands.append(" ".join(cmd))
        process = MagicMock()
        process.returncode = 0
        process.communicate = AsyncMock(return_value=(b"", b""))
        return process

    start_patch(context, "asyncio.create_subprocess_exec", side_effect=fake_exec)


@when("I write the configuration for the domain")
def step_write_config(context):
    context.loop.run_until_complete(nginx_manager.write_config(context.domain.domain, "server {}"))


@when("I reload nginx")
def step_reload(context):
    context.loop.run_until_complete(nginx_manager.reload())


@when('I remove the configuration of "{name}"')
def step_remove_config(context, name):
    context.loop.run_until_complete(nginx_manager.remove_config(name))


@when('I list the sudoers rules for user "{user}"')
def step_sudoers(context, user):
    context.sudoers = sudoers_lines(user)


@then('the recorded command is "{command}"')
def step_recorded_command(context, command):
    assert context.commands == [command.replace("<staging>", context.staging_dir)], context.commands


@then("the recorded commands are")
def step_recorded_commands(context):
    assert context.commands == context.text.splitlines(), context.commands


@then("the staging directory is empty")
def step_staging_empty(context):
    assert os.listdir(context.staging_dir) == []


@then('the sudoers rules include "{rule}"')
def step_sudoers_include(context, rule):
    assert rule in context.sudoers, context.sudoers


@then('the sudoers rule for "{command}" ends with a wildcard for the domain')
def step_sudoers_wildcard(context, command):
    (rule,) = [line for line in context.sudoers if f" {command} " in line + " "]
    assert rule.endswith(f" {command} *"), rule
