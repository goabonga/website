# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The matrices of the ci workflow, built from the selected components."""

import importlib.util
import io
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "ci_matrix.py"
spec = importlib.util.spec_from_file_location("ci_matrix", SCRIPT)
assert spec is not None and spec.loader is not None
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for path in ("apps/auth/features", "apps/billing", "libs/e2e-support"):
        (tmp_path / path).mkdir(parents=True)
    return tmp_path


def names(entries: list[dict[str, Any]], key: str = "check") -> list[str]:
    return [entry[key] for entry in entries]


def test_an_application_gets_its_checks_tests_and_scenarios(tree: Path) -> None:
    matrices = cm.build(["auth", "deploy-production"], tree)
    assert names(matrices["checks"]) == ["license", "lint", "format", "bandit", "audit", "osv"]
    assert {entry["target"] for entry in matrices["checks"]} == {"auth"}
    assert [e["package"] for e in matrices["checks"] if e["check"] in ("audit", "osv")] == [
        "auth",
        "auth",
    ]
    assert [e["package"] for e in matrices["checks"] if e["check"] == "lint"] == [""]
    assert matrices["tests"] == [
        {
            "target": "auth",
            "path": "apps/auth",
            "package": "auth",
            "browser": "auto",
            "codecov": "true",
        }
    ]
    assert matrices["behave"] == [{"target": "auth", "path": "apps/auth", "package": "auth"}]


def test_an_application_without_scenarios_has_no_behave_entry(tree: Path) -> None:
    matrices = cm.build(["billing"], tree)
    assert matrices["tests"][0]["target"] == "billing"
    assert matrices["behave"] == []


def test_the_library_scripts_and_groups(tree: Path) -> None:
    matrices = cm.build(["e2e-support", "scripts", "workflows", "workspace", "docs"], tree)
    by_target = {
        t: [e["check"] for e in matrices["checks"] if e["target"] == t]
        for t in ("e2e-support", "scripts", "workflows", "workspace")
    }
    assert by_target == {
        "e2e-support": ["license", "lint", "format", "bandit"],
        "scripts": ["license", "lint", "format"],
        "workflows": ["license"],
        "workspace": ["license"],
    }
    types = {e["target"]: e["types"] for e in matrices["checks"] if e["check"] == "license"}
    assert types == {
        "e2e-support": "py",
        "scripts": "py,sh",
        "workflows": "yml",
        "workspace": "toml",
    }
    assert [(e["target"], e["browser"], e["codecov"]) for e in matrices["tests"]] == [
        ("e2e-support", "true", "true"),
        ("scripts", "auto", "false"),
    ]
    assert matrices["behave"] == []


def test_nothing_selected_builds_empty_matrices(tree: Path) -> None:
    matrices = cm.build([], tree)
    assert matrices == {"checks": [], "tests": [], "behave": []}
    assert cm.build(["auth"], tree.parent / "missing")["checks"] == []


def test_outputs_are_matrices_and_flags(tree: Path) -> None:
    lines = cm.outputs(cm.build(["billing"], tree))
    values = dict(line.split("=", 1) for line in lines)
    assert json.loads(values["tests"])["include"][0]["target"] == "billing"
    assert values["has_checks"] == "true"
    assert values["has_tests"] == "true"
    assert values["has_behave"] == "false"
    assert values["behave"] == '{"include":[]}'


def test_main_reads_the_selection_from_the_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tree: Path
) -> None:
    monkeypatch.chdir(tree)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"changed": ["auth"]}'))
    cm.main()
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith('checks={"include":[{"target":"auth"')
    assert "has_behave=true" in out
