#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Re-author and GPG-sign a Dependabot commit as a Conventional Commit.

Run by `git rebase --exec` in dependabot-rewrite.yml, from the root of the
branch it rewrites. The type and the scope reflect what the bump affects.
The scope must come from the closed list in CLAUDE.md, so the usual `deps`
scope is not used:

  - GitHub Actions bumps                -> ci           (no scope)
  - the "dev-tools" group               -> chore(workspace)
  - a package declared by one app only  -> <type>(<app>)
  - a package declared by several apps  -> <type>       (no scope: a commit
    touching two scopes is not valid, and there is no cross-cutting scope)
  - root tooling or a transitive bump   -> chore(workspace)

<type> is fix when the package is a runtime dependency of an app (it ships
with the application, so it must release it: [project].dependencies or
[project.optional-dependencies] of apps/<app>/pyproject.toml) and chore when
it only appears in a dev group, either [dependency-groups].dev of the root
pyproject.toml or of the app pyproject whose dependencies are involved.
"""

import re
import subprocess
import tomllib
from pathlib import Path

LEADING_TYPE = re.compile(r"^[a-z]+(\([^)]+\))?!?:\s*")
SINGLE_BUMP = re.compile(r"^[Bb]ump ([A-Za-z0-9._-]+) from ")
TRAILER = re.compile(r"^co-authored-by:", re.I)
WORKSPACE = "chore(workspace)"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def requirement_name(spec: str) -> str:
    return normalize(re.split(r"[\[<>=~!;\s(@]", spec.strip(), maxsplit=1)[0])


def requirement_names(specs: list[object]) -> set[str]:
    return {requirement_name(spec) for spec in specs if isinstance(spec, str)}


def load(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def classify(package: str) -> str:
    """The `type` or `type(scope)` prefix of a bump of ``package``."""
    target = normalize(package)
    runtime_apps: set[str] = set()
    dev_apps: set[str] = set()
    for path in sorted(Path("apps").glob("*/pyproject.toml")):
        data = load(path)
        project = data.get("project", {})
        runtime = requirement_names(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            runtime |= requirement_names(extra)
        dev = requirement_names(data.get("dependency-groups", {}).get("dev", []))
        if target in runtime:
            runtime_apps.add(path.parent.name)
        elif target in dev:
            dev_apps.add(path.parent.name)
    apps = runtime_apps | dev_apps
    if len(apps) == 1:
        kind = "fix" if runtime_apps else "chore"
        return f"{kind}({next(iter(apps))})"
    if len(apps) > 1:
        return "fix" if runtime_apps else "chore"
    # Root tooling, or a transitive dependency: nothing is declared by an app.
    return WORKSPACE


def commit_type(changed: list[str], text: str) -> str:
    if any(".github/workflows/" in path for path in changed):
        return "ci"
    if re.search(r"dev-tools group", text, re.I):
        return WORKSPACE
    match = SINGLE_BUMP.match(text)
    return classify(match.group(1)) if match else WORKSPACE


def rewrite(changed: list[str], subject: str, body: str) -> str:
    """The Conventional Commit message of a Dependabot commit."""
    text = LEADING_TYPE.sub("", subject)
    body = "\n".join(line for line in body.splitlines() if not TRAILER.match(line)).strip()
    message = f"{commit_type(changed, text)}: {text}"
    return f"{message}\n\n{body}" if body else message


def main() -> None:
    changed = git("show", "--name-only", "--pretty=", "HEAD").splitlines()
    message = rewrite(
        changed, git("log", "-1", "--pretty=%s", "HEAD"), git("log", "-1", "--pretty=%b", "HEAD")
    )
    subprocess.run(
        ["git", "commit", "--amend", "--reset-author", "-m", message, "--quiet"], check=True
    )


if __name__ == "__main__":
    main()
