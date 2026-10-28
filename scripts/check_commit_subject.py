#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Check that commit messages follow the conventions of this repository.

The signed merge replays every commit through sign_commit.py, which refuses a
subject that is not a Conventional Commit, is longer than 72 characters or
ends with a period. This applies the same rule earlier, where it is cheap to
fix, and adds the rules of CLAUDE.md that the merge cannot enforce: the type
and the scope come from closed lists, and a message carries no attribution
trailer, tool signature or emoji. It runs as the commit-msg hook
(``check_commit_subject.py MESSAGE_FILE``) and in CI on the commits of a pull
request (``check_commit_subject.py --range BASE..HEAD``). The hook lets
autosquash commits (``fixup!``) through.
"""

import re
import subprocess
import sys

LIMIT = 72
TYPES = (
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "chore",
    "style",
    "perf",
    "build",
    "ci",
    "revert",
)
# The closed list of "Commit scopes" in CLAUDE.md, which
# tests/test_check_commit_subject.py keeps in step with this tuple. A scope is
# optional, but a scope that is given must be one of these.
SCOPES = (
    "analytics",
    "apt-server",
    "asterisk",
    "auth",
    "backend",
    "billing",
    "custom-domain",
    "frontend",
    "internal",
    "knowledge",
    "mailler",
    "mta-sts",
    "reachy-mini-api",
    "team",
    "vpn-portal",
    "webhooks",
    "ansible",
    "workspace",
    "multicz",
    "site",
)
# `git commit --fixup` and `--squash` subjects are meant to be squashed away
# before the pull request: only the commits CI looks at must be valid.
AUTOSQUASH = ("fixup! ", "squash! ", "amend! ")
SCISSORS = "# ------------------------ >8 ------------------------"

HEADER = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^()]*)\))?(?P<breaking>!)?: (?P<summary>.*)")
ATTRIBUTION = re.compile(r"^\s*(?:co-authored-by:|generated (?:with|by)\b)", re.I)
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE: \S", re.M)
EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⭐⭕⌚⌛⏩-⏳️‍]")


def problem(subject: str) -> str | None:
    """Why ``subject`` is refused, or None when it is valid."""
    if len(subject) > LIMIT:
        return f"{len(subject)} characters, the limit is {LIMIT}"
    if subject.endswith("."):
        return "ends with a period"
    match = HEADER.fullmatch(subject)
    if match is None:
        return "not `<type>(<scope>): <lowercase imperative summary>`"
    if match["type"] not in TYPES:
        return f"unknown type `{match['type']}`, expected one of {', '.join(TYPES)}"
    if match["scope"] is not None and match["scope"] not in SCOPES:
        return f"unknown scope `{match['scope']}`, see Commit scopes in CLAUDE.md"
    if not re.match(r"[a-z]", match["summary"]):
        return "the summary must start with a lowercase letter"
    return None


def message_problems(message: str) -> list[str]:
    """Every reason the commit ``message`` is refused (empty when valid)."""
    subject, _, rest = message.partition("\n")
    reasons = [reason] if (reason := problem(subject.rstrip())) else []
    if any(ATTRIBUTION.match(line) for line in message.splitlines()):
        reasons.append("carries a Co-Authored-By trailer or a tool attribution")
    if EMOJI.search(message):
        reasons.append("contains an emoji")
    match = HEADER.fullmatch(subject.rstrip())
    if match and match["breaking"] and not BREAKING_FOOTER.search(rest):
        reasons.append("`!` without a `BREAKING CHANGE:` footer")
    return reasons


def message_text(path: str) -> str:
    """A commit message file without its comment lines and what follows the scissors."""
    with open(path, encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    if SCISSORS in lines:
        lines = lines[: lines.index(SCISSORS)]
    return "\n".join(line for line in lines if not line.startswith("#")).strip()


def range_messages(commit_range: str) -> list[tuple[str, str]]:
    log = subprocess.check_output(
        ["git", "log", "--no-merges", "--format=%h%x1f%B%x1e", commit_range], text=True
    )
    pairs = (entry.strip("\n").split("\x1f", 1) for entry in log.split("\x1e") if entry.strip())
    return [(sha, message.strip()) for sha, message in pairs]


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--range":
        messages = range_messages(argv[1])
    elif len(argv) == 1 and not argv[0].startswith("-"):
        message = message_text(argv[0])
        messages = [] if message.startswith(AUTOSQUASH) else [("", message)]
    else:
        print("usage: check_commit_subject.py MESSAGE_FILE | --range BASE..HEAD")
        return 2
    failed = False
    for sha, message in messages:
        for reason in message_problems(message):
            failed = True
            print(f"{sha} {message.partition(chr(10))[0]!r}: {reason}".strip())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
