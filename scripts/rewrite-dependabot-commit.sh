#!/usr/bin/env bash

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

# Re-author and GPG-sign a Dependabot commit, normalising its subject to
# Conventional Commits with a type and a scope that reflect what the bump
# affects. Run by `git rebase --exec` in dependabot-rewrite.yml, from the
# repository root.
#
# The scope must come from the closed list in CLAUDE.md, so the usual "deps"
# scope is not used. Instead:
#   - GitHub Actions bumps                -> ci           (no scope)
#   - the "dev-tools" group               -> chore(workspace)
#   - a package declared by one app only  -> <type>(<app>)
#   - a package declared by several apps  -> <type>       (no scope: a commit
#     touching two scopes is not valid, and there is no cross-cutting scope)
#   - root tooling or a transitive bump   -> chore(workspace)
#
# <type> is fix when the package is a runtime dependency of an app (it ships
# with the application, so it must release it: [project].dependencies or
# [project.optional-dependencies] of apps/<app>/pyproject.toml) and chore when
# it only appears in a dev group, either [dependency-groups].dev of the root
# pyproject.toml or of the app pyproject whose dependencies are involved.

set -euo pipefail

changed=$(git show --name-only --pretty='' HEAD)
subject=$(git log -1 --pretty=%s HEAD)
body=$(git log -1 --pretty=%b HEAD | sed '/^[Cc]o-authored-by:/d')

# Drop any leading conventional prefix Dependabot already added.
text=$(printf '%s' "$subject" | sed -E 's/^[a-z]+(\([^)]+\))?!?:[[:space:]]*//')

classify() {
    # Prints the "type" or "type(scope)" prefix for the package name in $1.
    python3 - "$1" <<'PY'
import re
import sys
import tomllib
from pathlib import Path

pkg = sys.argv[1]


def norm(spec: str) -> str:
    name = re.split(r"[\[<>=~!;\s(@]", spec.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def names(specs) -> set[str]:
    return {norm(s) for s in specs if isinstance(s, str)}


def load(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


target = norm(pkg)
runtime_apps: set[str] = set()
dev_apps: set[str] = set()

for path in sorted(Path("apps").glob("*/pyproject.toml")):
    data = load(path)
    app = path.parent.name
    project = data.get("project", {})
    runtime = names(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        runtime |= names(extra)
    dev = names(data.get("dependency-groups", {}).get("dev", []))
    if target in runtime:
        runtime_apps.add(app)
    elif target in dev:
        dev_apps.add(app)

root_dev = names(load(Path("pyproject.toml")).get("dependency-groups", {}).get("dev", []))

apps = runtime_apps | dev_apps
if len(apps) == 1:
    app = next(iter(apps))
    print(f"fix({app})" if runtime_apps else f"chore({app})")
elif len(apps) > 1:
    print("fix" if runtime_apps else "chore")
elif target in root_dev:
    print("chore(workspace)")
else:
    # Transitive dependency: only uv.lock changes, nothing is declared.
    print("chore(workspace)")
PY
}

if printf '%s' "$changed" | grep -q '[.]github/workflows/'; then
    prefix="ci"
elif printf '%s' "$text" | grep -qiE 'dev-tools group'; then
    prefix="chore(workspace)"
else
    # Single-package bump: "bump <pkg> from X to Y".
    pkg=$(printf '%s' "$text" | sed -nE 's/^[Bb]ump ([A-Za-z0-9._-]+) from .*/\1/p')
    if [ -n "$pkg" ]; then
        prefix=$(classify "$pkg")
    else
        prefix="chore(workspace)"
    fi
fi

if [ -n "$body" ]; then
    new_msg=$(printf '%s: %s\n\n%s' "$prefix" "$text" "$body")
else
    new_msg=$(printf '%s: %s' "$prefix" "$text")
fi

git commit --amend --reset-author -m "$new_msg" --quiet
