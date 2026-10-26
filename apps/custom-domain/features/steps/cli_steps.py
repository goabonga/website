# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the command line interface feature."""

import shlex
from unittest.mock import AsyncMock

from behave import given, then, when
from click.testing import CliRunner
from custom_domain.cli import cli
from custom_domain.models import AuthorizedClient, NginxTemplate
from environment import start_patch
from fakes import AsyncSessionShim
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def run(context, command):
    if not hasattr(context, "cli_patched"):
        start_patch(
            context,
            "custom_domain.cli.get_session",
            new=AsyncMock(
                side_effect=lambda: AsyncSessionShim(
                    Session(context.db.engine, expire_on_commit=False)
                )
            ),
        )
        context.cli_patched = True
    context.cli_result = CliRunner().invoke(cli, shlex.split(command))


@given('I ran the command "{command}"')
def step_ran(context, command):
    run(context, command)
    assert context.cli_result.exit_code == 0, context.cli_result.output


@when('I run the command "{command}"')
def step_run(context, command):
    run(context, command)


@then("the command succeeds")
def step_succeeds(context):
    assert context.cli_result.exit_code == 0, context.cli_result.output


@then("the command fails")
def step_fails(context):
    assert context.cli_result.exit_code != 0


@then('the output contains "{text}"')
def step_output(context, text):
    assert text in context.cli_result.output, context.cli_result.output


@then("the default template exists with the packaged HTTP and HTTPS sources")
def step_default_template(context):
    with context.db.session() as session:
        template = session.scalar(select(NginxTemplate).where(NginxTemplate.is_default.is_(True)))
    assert template.slug == "default"
    assert "acme-challenge" in template.http_template
    assert "ssl_certificate" in template.https_template


@then("there is {count:d} template in the database")
def step_template_count(context, count):
    with context.db.session() as session:
        assert session.scalar(select(func.count()).select_from(NginxTemplate)) == count


@then('the client "{client_id}" is stored with {limit:d} maximum domains')
def step_client_stored(context, client_id, limit):
    with context.db.session() as session:
        client = session.scalar(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        )
    assert client.max_domains == limit
