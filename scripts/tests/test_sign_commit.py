# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The commit re-signing helper run by git rebase --exec."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sign = load("sign_commit")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("feat: add x", "feat: add x\n"),
        ("feat(cli)!: add x", "feat(cli): add x\n"),
        ("remove: drop y", "remove: drop y\n"),
        (
            "fix: a\n\nBody.\nCo-Authored-By: bot <b@x.y>\nBREAKING CHANGE: no\n"
            "Generated with a tool",
            "fix: a\n\nBody.\n",
        ),
    ],
)
def test_commit_messages_are_cleaned(raw: str, expected: str) -> None:
    assert sign.clean_message(raw) == expected


@pytest.mark.parametrize(
    "subject", ["Add x", "feat: Add x", "feat: add x.", "wip: x", "feat: " + "a" * 70]
)
def test_invalid_subjects_are_refused(subject: str) -> None:
    with pytest.raises(SystemExit, match="invalid Conventional Commit"):
        sign.clean_message(subject)
