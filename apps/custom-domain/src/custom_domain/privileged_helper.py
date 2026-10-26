#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Root-side helper that performs the few privileged operations of the service.

The API and the Celery worker never run as root. Everything that needs privileges
(writing and removing nginx virtual hosts, testing and reloading nginx) goes through this one script,
which the worker starts with ``sudo``. It is the only thing the sudoers rule has
to allow, and it validates everything it is given:

* every option (paths, binaries, prefix, e-mail) must be one of a fixed set and
  is validated; the sudoers line fixes their values, so the caller can not
  change them;
* the single positional argument is a lower-case domain name or a 32 character
  hexadecimal token and nothing else;
* files to install are read from the staging directory under a name that is
  computed here, never given by the caller.

The module only uses the standard library so that it can be installed on its own
(owned by root, mode 0755) and run with the system interpreter. The application
imports :data:`COMMANDS` to build the command lines and the sudoers rules from the
same table.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

EXIT_USAGE = 64
EXIT_NOT_FOUND = 3
# Upper bound of a staged configuration file, a safety limit rather than a setting.
MAX_STAGED_BYTES = 1_048_576

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._-]{0,63}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,63}$")


class UsageError(Exception):
    """The command line is not one this helper accepts."""


def _is_root() -> bool:
    return os.geteuid() == 0


def _absolute_path(value: str) -> str:
    if not value.startswith("/") or "\0" in value or os.path.normpath(value) != value.rstrip("/"):
        raise UsageError(f"not a normalized absolute path: {value!r}")
    return value


def _directory(value: str) -> str:
    return _absolute_path(value)


def _regex(pattern: re.Pattern[str], what: str) -> Callable[[str], str]:
    def check(value: str) -> str:
        if not pattern.fullmatch(value):
            raise UsageError(f"invalid {what}: {value!r}")
        return value

    return check


# Option name -> validator. The sudoers rules fix the value of every option.
OPTIONS: dict[str, Callable[[str], str]] = {
    "sites-dir": _directory,
    "config-prefix": _regex(PREFIX_RE, "file prefix"),
    "staging-dir": _directory,
    "nginx-bin": _absolute_path,
    "nginx-service": _regex(UNIT_RE, "service name"),
    "systemctl-bin": _absolute_path,
}


def _trusted_executable(path: str) -> str:
    """Return ``path`` if it is a regular executable that only root can modify."""
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise UsageError(f"not an executable file: {path}")
    if _is_root() and (info.st_uid != 0 or info.st_mode & 0o022):
        raise UsageError(f"executable is not owned by root or is writable: {path}")
    return path


def _read_staged(directory: str, name: str) -> bytes:
    """Read a regular, non-symlink file the worker staged for installation."""
    fd = os.open(os.path.join(directory, name), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_STAGED_BYTES:
            raise UsageError(f"staged file is not a regular file of acceptable size: {name}")
        with os.fdopen(os.dup(fd), "rb") as handle:
            return handle.read()
    finally:
        os.close(fd)


def _environment() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")}


def _run(argv: list[str]) -> int:
    """Run a command, letting its output through, and return its exit status."""
    return subprocess.run(
        argv, check=False, env=_environment(), stdin=subprocess.DEVNULL
    ).returncode


def _config_name(opts: dict[str, str], domain: str) -> str:
    return f"{opts['config-prefix']}{domain}.conf"


def install_config(opts: dict[str, str], domain: str) -> int:
    """Install the staged virtual host of ``domain`` into the nginx sites directory."""
    name = _config_name(opts, domain)
    data = _read_staged(opts["staging-dir"], name)
    descriptor, temporary = tempfile.mkstemp(dir=opts["sites-dir"], prefix=".incoming-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), 0o644)
            if _is_root():
                os.fchown(handle.fileno(), 0, 0)
        os.replace(temporary, os.path.join(opts["sites-dir"], name))
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return 0


def delete_config(opts: dict[str, str], domain: str) -> int:
    """Remove the virtual host of ``domain`` if there is one."""
    Path(opts["sites-dir"], _config_name(opts, domain)).unlink(missing_ok=True)
    return 0


def check_nginx(opts: dict[str, str], _argument: str) -> int:
    """Check the whole nginx configuration."""
    return _run([_trusted_executable(opts["nginx-bin"]), "-t"])


def reload_nginx(opts: dict[str, str], _argument: str) -> int:
    """Reload nginx through systemd."""
    return _run([_trusted_executable(opts["systemctl-bin"]), "reload", opts["nginx-service"]])


def check_snippet(opts: dict[str, str], token: str) -> int:
    """Check that a staged template renders to something nginx accepts.

    The staged text is copied into a private directory and wrapped in the
    ``events``/``http`` contexts that a virtual host needs to be tested alone.
    """
    data = _read_staged(opts["staging-dir"], f"validate-{token}.conf")
    with tempfile.TemporaryDirectory() as private:
        snippet = Path(private, "snippet.conf")
        snippet.write_bytes(data)
        harness = Path(private, "nginx.conf")
        harness.write_text(f"events {{}}\nhttp {{\n    include {snippet};\n}}\n")
        return _run([_trusted_executable(opts["nginx-bin"]), "-t", "-c", str(harness)])


@dataclass(frozen=True)
class Command:
    """A subcommand: the options it needs, the kind of argument it takes, its action."""

    options: tuple[str, ...]
    argument: str | None
    action: Callable[..., int]


COMMANDS: dict[str, Command] = {
    "write-config": Command(
        ("sites-dir", "config-prefix", "staging-dir"), "domain", install_config
    ),
    "remove-config": Command(("sites-dir", "config-prefix"), "domain", delete_config),
    "test-nginx": Command(("nginx-bin",), None, check_nginx),
    "reload-nginx": Command(("systemctl-bin", "nginx-service"), None, reload_nginx),
    "check-snippet": Command(("nginx-bin", "staging-dir"), "token", check_snippet),
}

ARGUMENT_PATTERNS = {"domain": DOMAIN_RE, "token": TOKEN_RE}


def parse(argv: list[str]) -> tuple[Command, dict[str, str], str | None]:
    """Validate a command line and return the command, its options and its argument."""
    options: dict[str, str] = {}
    position = 0
    while position < len(argv) and argv[position].startswith("--"):
        name = argv[position][2:]
        if name not in OPTIONS or name in options or position + 1 >= len(argv):
            raise UsageError(f"unexpected option: {argv[position]}")
        options[name] = OPTIONS[name](argv[position + 1])
        position += 2
    rest = argv[position:]
    if not rest or rest[0] not in COMMANDS:
        raise UsageError("unknown command")
    command = COMMANDS[rest[0]]
    if set(options) != set(command.options):
        raise UsageError(f"{rest[0]} takes exactly the options: {', '.join(command.options)}")
    expected = 0 if command.argument is None else 1
    if len(rest) - 1 != expected:
        raise UsageError(f"{rest[0]} takes {expected} argument(s)")
    argument = None
    if command.argument is not None:
        argument = rest[1]
        if not ARGUMENT_PATTERNS[command.argument].fullmatch(argument):
            raise UsageError(f"invalid {command.argument}: {argument!r}")
    return command, options, argument


def main(argv: list[str] | None = None) -> int:
    """Entry point: validate the command line, then run the command."""
    arguments = sys.argv[1:] if argv is None else argv
    try:
        command, options, argument = parse(arguments)
        return command.action(options, argument or "")
    except UsageError as error:
        print(f"custom-domain-privileged: {error}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as error:
        print(f"custom-domain-privileged: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
