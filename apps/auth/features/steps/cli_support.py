# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Run the ``auth`` command line in process, for the scenarios of the deployment commands."""

import contextlib
import io
import shlex

import auth.cli  # noqa: F401  (imported before the database is routed to the scenario)
from auth.cli import main


def run_command(context, command, *extra):
    """Run an ``auth`` command line and keep its streams and exit status on the context."""
    argv = shlex.split(command)
    assert argv[0] == "auth", command
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = main([*argv[1:], *extra])
        except SystemExit as exc:
            status = exc.code
    context.command_status = status
    context.command_stdout = out.getvalue()
    context.command_stderr = err.getvalue()
