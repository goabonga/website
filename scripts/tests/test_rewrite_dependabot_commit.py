# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The scope-aware rewrite of Dependabot commits run by git rebase --exec."""

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).parent.parent


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rewrite = load("rewrite_dependabot_commit")


def app(root: Path, name: str, runtime: str = "", extra: str = "", dev: str = "") -> None:
    """Write apps/<name>/pyproject.toml declaring the given dependency lists."""
    directory = root / "apps" / name
    directory.mkdir(parents=True)
    optional = f"[project.optional-dependencies]\nextra = [{extra}]\n" if extra else ""
    (directory / "pyproject.toml").write_text(
        f"[project]\nname = '{name}'\ndependencies = [{runtime}]\n{optional}"
        f"[dependency-groups]\ndev = [{dev}]\n"
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'website'\n[dependency-groups]\ndev = ['ruff>=0.13', 'pytest>=8']\n"
    )
    app(tmp_path, "auth", runtime='"requests>=2", "Some_Lib[extra]~=1.0"', dev='"httpx>=0.27"')
    app(tmp_path, "team", runtime='"requests>=2"', extra='"pillow>=10"', dev='"httpx>=0.27"')
    app(tmp_path, "billing", dev='"respx>=0.2"')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("spec", "name"),
    [
        ("ruff>=0.13", "ruff"),
        ("Some_Tool[extra]~=1.0", "some-tool"),
        ("a;python_version<'3.12'", "a"),
        ("pkg @ https://example.org/pkg.whl", "pkg"),
        ("b", "b"),
    ],
)
def test_requirement_name(spec: str, name: str) -> None:
    assert rewrite.requirement_name(spec) == name


@pytest.mark.parametrize(
    ("package", "prefix"),
    [
        ("some_lib", "fix(auth)"),
        ("Some.Lib", "fix(auth)"),
        ("respx", "chore(billing)"),
        ("requests", "fix"),
        ("httpx", "chore"),
        ("pillow", "fix(team)"),
        ("ruff", "chore(workspace)"),
        ("virtualenv", "chore(workspace)"),
    ],
)
@pytest.mark.usefixtures("workspace")
def test_classify(package: str, prefix: str) -> None:
    assert rewrite.classify(package) == prefix


@pytest.mark.parametrize(
    ("changed", "text", "expected"),
    [
        ([".github/workflows/ci.yml"], "bump actions/checkout from 6 to 7", "ci"),
        (["uv.lock"], "bump the dev-tools group with 2 updates", "chore(workspace)"),
        (["uv.lock"], "bump ruff from 0.1 to 0.2", "chore(workspace)"),
        (["uv.lock"], "bump some-lib from 1 to 2", "fix(auth)"),
        (["uv.lock"], "Bump requests from 1 to 2", "fix"),
        (["uv.lock"], "update something", "chore(workspace)"),
    ],
)
@pytest.mark.usefixtures("workspace")
def test_commit_type(changed: list[str], text: str, expected: str) -> None:
    assert rewrite.commit_type(changed, text) == expected


@pytest.mark.usefixtures("workspace")
def test_rewrite_normalizes_the_subject_and_drops_co_authors() -> None:
    message = rewrite.rewrite(
        ["uv.lock"],
        "build(deps): bump some-lib from 1 to 2",
        "Details.\nCo-authored-by: bot <b@x.y>\n",
    )
    assert message == "fix(auth): bump some-lib from 1 to 2\n\nDetails."


@pytest.mark.usefixtures("workspace")
def test_rewrite_without_a_body() -> None:
    assert (
        rewrite.rewrite(["uv.lock"], "Bump ruff from 1 to 2", "")
        == "chore(workspace): Bump ruff from 1 to 2"
    )


@pytest.mark.usefixtures("workspace")
def test_main_amends_the_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        ("show", "--name-only", "--pretty=", "HEAD"): "uv.lock\n",
        ("log", "-1", "--pretty=%s", "HEAD"): "Bump some-lib from 1 to 2",
        ("log", "-1", "--pretty=%b", "HEAD"): "",
    }
    monkeypatch.setattr(rewrite, "git", lambda *args: answers[args])
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a[0], k)))
    rewrite.main()
    assert calls == [
        (
            [
                "git",
                "commit",
                "--amend",
                "--reset-author",
                "-m",
                "fix(auth): Bump some-lib from 1 to 2",
                "--quiet",
            ],
            {"check": True},
        )
    ]


def test_git_returns_stripped_output() -> None:
    assert rewrite.git("--version").startswith("git version")


def test_rewritten_subjects_are_valid_commit_messages() -> None:
    check = load("check_commit_subject")
    for prefix in ("ci", "fix", "chore", "fix(auth)", "chore(workspace)"):
        assert check.problem(f"{prefix}: bump some-lib from 1 to 2") is None
