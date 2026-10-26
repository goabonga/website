# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the command line scenarios.

The command line runs in-process against the scenario database.
"""

import contextlib
import io
import json
import shlex
import tempfile
from pathlib import Path

from behave import given, then, when
from mailler import cli

MJML = (
    "<mjml><mj-body><mj-section><mj-column><mj-text>Hello {{ name }}"
    "</mj-text></mj-column></mj-section></mj-body></mjml>"
)


@when("I run the command line: {command}")
def step_run_command_line(context, command):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(
                shlex.split(
                    command.replace("{templates_dir}", getattr(context, "templates_dir", ""))
                )
            )
        except SystemExit as exit_:
            code = exit_.code
    context.cli_code, context.cli_out, context.cli_err = code, out.getvalue(), err.getvalue()


@given("a directory with the templates")
def step_templates_directory(context):
    """Create ``<slug>.mjml`` and ``<slug>.json`` files; columns: slug, subject, extra (JSON)."""
    directory = Path(tempfile.mkdtemp(prefix="mailler-templates-"))
    for row in context.table:
        slug = row["slug"]
        (directory / f"{slug}.mjml").write_text(row["mjml"] if "mjml" in row.headings else MJML)
        description = {"subject_template": row["subject"]}
        if "extra" in row.headings and row["extra"]:
            description.update(json.loads(row["extra"]))
        (directory / f"{slug}.json").write_text(json.dumps(description))
    context.templates_dir = str(directory)


@then("the command should succeed")
def step_command_succeeds(context):
    assert context.cli_code == 0, (context.cli_code, context.cli_out, context.cli_err)


@then("the command should fail with exit code {code:d}")
def step_command_fails(context, code):
    assert context.cli_code == code, (context.cli_code, context.cli_out, context.cli_err)


@then('the command output should contain "{text}"')
def step_command_output(context, text):
    assert text in context.cli_out, context.cli_out


@then('the command error should contain "{text}"')
def step_command_error(context, text):
    assert text in context.cli_err, context.cli_err


@then('the command output should not contain "{text}"')
def step_command_output_absent(context, text):
    assert text not in context.cli_out, context.cli_out
