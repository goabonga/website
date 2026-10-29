#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Build the matrices of the ci workflow from the components `detect` selected.

The workflow runs its checks, its unit tests and its behave scenarios through
three matrices. This turns the list of selected components (``{"changed": [...]}``,
read from the standard input) into the three matrices and the flags that tell
whether each one has anything to run, written as ``name=value`` lines for
``$GITHUB_OUTPUT``. An application gets the six checks, its unit tests and, when
it has a ``features`` directory, its behave scenarios; ``e2e-support``, the scripts and
the groups of files only get the checks that apply to them.
"""

import json
import sys
from pathlib import Path
from typing import Any

APP_CHECKS = ("license", "lint", "format", "bandit", "audit", "osv")
LIBRARY = "e2e-support"
LIBRARY_CHECKS = ("license", "lint", "format", "bandit")
SCRIPTS_CHECKS = ("license", "lint", "format")

Entry = dict[str, Any]


def check(target: str, name: str, path: str, package: str = "", types: str = "py") -> Entry:
    return {"target": target, "check": name, "path": path, "package": package, "types": types}


def build(changed: list[str], root: Path = Path()) -> dict[str, list[Entry]]:
    """The entries of the three matrices for the selected components."""
    selected = set(changed)
    checks: list[Entry] = []
    tests: list[Entry] = []
    behave: list[Entry] = []
    apps = (
        sorted(p.name for p in (root / "apps").iterdir() if p.is_dir())
        if (root / "apps").is_dir()
        else []
    )
    for app in apps:
        if app not in selected:
            continue
        path = f"apps/{app}"
        checks += [
            check(app, name, path, package=app if name in ("audit", "osv") else "")
            for name in APP_CHECKS
        ]
        tests.append(
            {"target": app, "path": path, "package": app, "browser": "auto", "codecov": "true"}
        )
        if (root / path / "features").is_dir():
            behave.append({"target": app, "path": path, "package": app})
    if LIBRARY in selected:
        path = f"libs/{LIBRARY}"
        checks += [check(LIBRARY, name, path) for name in LIBRARY_CHECKS]
        tests.append(
            {
                "target": LIBRARY,
                "path": path,
                "package": LIBRARY,
                "browser": "true",
                "codecov": "true",
            }
        )
    if "scripts" in selected:
        checks += [check("scripts", name, "scripts", types="py,sh") for name in SCRIPTS_CHECKS]
        tests.append(
            {
                "target": "scripts",
                "path": "scripts",
                "package": "",
                "browser": "auto",
                "codecov": "false",
            }
        )
    if "workflows" in selected:
        checks.append(check("workflows", "license", ".github", types="yml"))
    if "workspace" in selected:
        checks.append(check("workspace", "license", ".", types="toml"))
    return {"checks": checks, "tests": tests, "behave": behave}


def outputs(matrices: dict[str, list[Entry]]) -> list[str]:
    """The `name=value` lines: each matrix as JSON and whether it has an entry."""
    lines: list[str] = []
    for name, entries in matrices.items():
        lines.append(f"{name}={json.dumps({'include': entries}, separators=(',', ':'))}")
        lines.append(f"has_{name}={'true' if entries else 'false'}")
    return lines


def main() -> None:
    changed = json.load(sys.stdin).get("changed", [])
    sys.stdout.write("\n".join(outputs(build(changed))) + "\n")


if __name__ == "__main__":
    main()
