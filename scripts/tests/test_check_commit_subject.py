# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The commit message check run by pre-commit and by the ci workflow."""

import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).parent.parent
ROOT = SCRIPTS.parent


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load("check_commit_subject")
sign = load("sign_commit")

LONG = "test(auth): cover " + "x" * 55


def claude_scopes() -> set[str]:
    """The scopes listed under "Commit scopes" in CLAUDE.md."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    section = text.split("## Commit scopes", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"`([a-z][a-z0-9-]*)`", section))


def test_the_scopes_are_those_of_claude_md() -> None:
    assert set(check.SCOPES) == claude_scopes()


def test_every_application_is_a_scope() -> None:
    applications = {path.name for path in (ROOT / "apps").iterdir() if path.is_dir()}
    assert applications <= set(check.SCOPES)


def test_the_types_are_the_closed_list_of_the_global_rules() -> None:
    assert set(check.TYPES) == {
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
    }


@pytest.mark.parametrize(
    "subject",
    [
        "fix: handle an empty plan",
        "feat(auth): add a flag",
        "chore(workspace): bump ruff from 1 to 2",
        "fix(mta-sts): serve the policy",
        "refactor(auth)!: drop the old api",
        "ci: bump actions/checkout from 5 to 6",
        "test(auth): " + "x" * 60,
    ],
)
def test_valid_subjects(subject: str) -> None:
    assert check.problem(subject) is None


@pytest.mark.parametrize(
    ("subject", "reason"),
    [
        (LONG, "73 characters"),
        ("fix(auth): handle an empty plan.", "period"),
        ("Fix(auth): handle an empty plan", "not `<type>"),
        ("fix(auth): Handle an empty plan", "lowercase"),
        ("wip(auth): handle an empty plan", "unknown type"),
        ("deprecate(auth): handle an empty plan", "unknown type"),
        ("fix(deps): bump requests from 1 to 2", "unknown scope `deps`"),
        ("fix(Auth): handle an empty plan", "unknown scope"),
        ("fix(): handle an empty plan", "unknown scope"),
        ("handle an empty plan", "not `<type>"),
        ("", "not `<type>"),
    ],
)
def test_invalid_subjects(subject: str, reason: str) -> None:
    assert reason in str(check.problem(subject))


def test_a_subject_valid_here_is_accepted_by_the_signed_merge() -> None:
    subject = "fix(auth): handle an empty plan"
    assert check.problem(subject) is None
    assert sign.clean_message(subject) == subject + "\n"


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("fix(auth): a change\n\nCo-Authored-By: Someone <a@b.c>", "Co-Authored-By"),
        ("fix(auth): a change\n\nco-authored-by: Someone <a@b.c>", "Co-Authored-By"),
        ("fix(auth): a change\n\nGenerated with a tool", "attribution"),
        ("fix(auth): a change\n\nbody \U0001f600", "emoji"),
        ("fix(auth): a change ✅", "emoji"),
        ("feat(auth)!: drop a flag", "BREAKING CHANGE"),
        ("feat(auth)!: drop a flag\n\nBREAKING CHANGE:", "BREAKING CHANGE"),
    ],
)
def test_invalid_messages(message: str, reason: str) -> None:
    assert any(reason in found for found in check.message_problems(message))


@pytest.mark.parametrize(
    "message",
    [
        "fix(auth): a change",
        "fix(auth): a change\n\nwhy it changes\n\nRefs: #12\nCloses: #13",
        "feat(auth)!: drop a flag\n\nwhy\n\nBREAKING CHANGE: the flag is gone",
        "fix(auth): a change\n\nthe arrow → and a dash — are not emoji",
    ],
)
def test_valid_messages(message: str) -> None:
    assert check.message_problems(message) == []


def test_every_problem_of_a_message_is_reported() -> None:
    message = "Fix(deps): Nope.\n\nCo-Authored-By: Someone <a@b.c>\n\n\U0001f600"
    assert len(check.message_problems(message)) == 3


def test_the_text_of_a_message_file_skips_comments_and_the_diff(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        "\n# Please enter the commit message\nfix(auth): a change\n\nbody\n"
        f"# Everything below is dropped\n{check.SCISSORS}\ndiff --git a/x b/x\n+Co-Authored-By: x\n"
    )
    assert check.message_text(str(message)) == "fix(auth): a change\n\nbody"


@pytest.mark.parametrize("prefix", ["fixup! ", "squash! ", "amend! "])
def test_the_hook_lets_autosquash_commits_through(tmp_path: Path, prefix: str) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"{prefix}fix(auth): a change that is squashed away later on.\n")
    assert check.main([str(message)]) == 0


def test_an_empty_message_file_is_refused(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("# only a comment\n")
    assert check.message_text(str(message)) == ""
    assert check.main([str(message)]) == 1


def test_the_hook_mode_checks_the_message_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix(auth): a change\n")
    assert check.main([str(message)]) == 0
    message.write_text(LONG + "\n")
    assert check.main([str(message)]) == 1
    assert "73 characters" in capsys.readouterr().out


def test_the_range_mode_reports_every_invalid_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.name", "Chris")
    git("config", "user.email", "chris@example.org")
    git("config", "commit.gpgsign", "false")
    git("commit", "-q", "--allow-empty", "-m", "chore(workspace): base")
    for message in (
        "fix(auth): a change",
        "Fix(auth): a change.",
        LONG,
        "fix(auth): a change\n\nCo-Authored-By: Someone <a@b.c>",
    ):
        git("commit", "-q", "--allow-empty", "-m", message)
    assert check.main(["--range", "HEAD~4..HEAD"]) == 1
    out = capsys.readouterr().out
    assert "a change.'" in out and "73 characters" in out and "Co-Authored-By" in out
    assert out.count("\n") == 3
    assert check.main(["--range", "HEAD~4..HEAD~3"]) == 0


def test_arguments_are_validated(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main([]) == 2
    assert check.main(["--range"]) == 2
    assert "usage" in capsys.readouterr().out
