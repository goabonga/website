# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Run privileged operations through the root-side helper.

This is the only place where the service starts a command with ``sudo``. Every
privileged operation is one command of :mod:`custom_domain.privileged_helper`,
started as ``sudo -n <helper> <fixed options> <command> [<argument>]``. The fixed
options come from the settings, so the sudoers rule that allows the helper is
generated from the same table (see :func:`sudoers_lines`).
"""

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from custom_domain import privileged_helper
from custom_domain.config import require_setting, settings
from custom_domain.logging import get_logger

logger = get_logger(__name__)

# Helper option -> name of the setting that provides its value.
OPTION_SETTINGS = {
    "sites-dir": "nginx_sites_dir",
    "config-prefix": "nginx_config_prefix",
    "staging-dir": "privileged_staging_dir",
    "nginx-bin": "nginx_bin",
    "nginx-service": "nginx_service",
    "systemctl-bin": "systemctl_bin",
}


@dataclass
class PrivilegedResult:
    """Outcome of one helper command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """Whether the command succeeded."""
        return self.returncode == 0


def helper_arguments(command: str, argument: str | None = None) -> list[str]:
    """Build the arguments that follow the helper path for ``command``.

    Raises:
        ConfigurationError: If a setting the command needs is empty
        KeyError: If ``command`` is not a helper command
    """
    spec = privileged_helper.COMMANDS[command]
    arguments: list[str] = []
    for option in spec.options:
        arguments += [f"--{option}", require_setting(OPTION_SETTINGS[option], settings)]
    arguments.append(command)
    if argument is not None:
        arguments.append(argument)
    return arguments


def build_command(command: str, argument: str | None = None) -> list[str]:
    """Build the full ``sudo`` command line for one helper command."""
    helper = require_setting("privileged_helper", settings)
    return [
        require_setting("sudo_bin", settings),
        "-n",
        helper,
        *helper_arguments(command, argument),
    ]


async def run_privileged(command: str, argument: str | None = None) -> PrivilegedResult:
    """Run one helper command and wait for it.

    Raises:
        ConfigurationError: If a setting the command needs is empty
        TimeoutError: If the helper does not finish in ``PRIVILEGED_TIMEOUT_SECONDS``
    """
    argv = build_command(command, argument)
    logger.info("Running privileged command %s", command)
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=settings.privileged_timeout_seconds
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return PrivilegedResult(
        returncode=process.returncode if process.returncode is not None else 1,
        stdout=stdout.decode() if stdout else "",
        stderr=stderr.decode() if stderr else "",
    )


def stage_file(name: str, content: str) -> Path:
    """Write ``content`` to the staging directory for the helper to install or check.

    The helper reads it back from the same directory under the same name, which it
    computes itself, so the file is never passed to it by path.
    """
    directory = Path(require_setting("privileged_staging_dir", settings))
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o640)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(content)
    return path


def _sudoers_escape(value: str) -> str:
    """Escape the characters that have a meaning in a sudoers command line."""
    return "".join(f"\\{c}" if c in ' ,:=\\"#' else c for c in value)


def sudoers_lines(user: str) -> list[str]:
    """Return the sudoers rules that allow ``user`` to run exactly the helper commands.

    Commands without an argument are allowed as one exact command line. Commands
    with a domain or token argument end with ``*``: sudo matches the fixed options
    literally and the helper validates the argument itself.
    """
    lines: list[str] = []
    for command, spec in privileged_helper.COMMANDS.items():
        words = [
            require_setting("privileged_helper", settings),
            *helper_arguments(command),
        ]
        rule = " ".join(_sudoers_escape(word) for word in words)
        if spec.argument is not None:
            rule += " *"
        lines.append(f"{user} ALL=(root) NOPASSWD: {rule}")
    return lines


def main(argv: list[str] | None = None) -> None:
    """Print the sudoers rules for the configured helper (``python -m``)."""
    parser = argparse.ArgumentParser(description="Print the sudoers rules for the helper")
    parser.add_argument("--user", required=True, help="System user that runs the worker")
    for line in sudoers_lines(parser.parse_args(argv).user):
        print(line)


if __name__ == "__main__":
    main()
