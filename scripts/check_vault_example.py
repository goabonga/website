#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Check that the example vault lists exactly the variables the repository uses.

Every ``vault_*`` variable referenced in ``ansible/``, ``deploy/`` or ``docs/``
must be defined in ``vault.yml.example``, and every variable of the example
must be referenced somewhere, so that the file neither misses a variable nor
keeps a dead one. A variable is defined by a line ``name: value``, commented
out or not (a commented one belongs to an application or a role that the
example does not enable). Besides the names, the check enforces three rules:

* a value of the example is a placeholder (``CHANGE_ME``) or empty;
* each secret the application catalog asks for (``secret_names`` and
  ``optional_secret_names``) appears in the table of the Secrets page;
* a ``vault.yml`` committed in the repository is encrypted.

Run it from anywhere: ``check_vault_example.py [ROOT]`` (default: the root of
the repository). Exit status 1 lists the problems.
"""

import re
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path("ansible/examples/inventory/group_vars/all/vault.yml.example")
CATALOG = Path("ansible/roles/python_app/defaults/main/catalog.yml")
SECRETS_PAGE = Path("docs/ansible/03-secrets.md")
SCANNED = ("ansible", "deploy", "docs")
SUFFIXES = {".yml", ".yaml", ".md", ".j2", ".cfg", ".example", ".toml"}

# Not variables of the vault: the Ansible setting and the name of the file.
NOT_VARIABLES = {"vault_pass", "vault_password_file"}
# Placeholders of the documentation, for an application or a user of your own.
PLACEHOLDER_PREFIXES = ("vault_my_app_", "vault_alice_")

NAME = re.compile(r"\bvault_[a-z0-9_]+\b")
DEFINITION = re.compile(r"^(?:# )?(vault_[a-z0-9_]+):[ \t]*(.*?)[ \t]*$", re.MULTILINE)
CATALOG_SECRETS = re.compile(r"^\s*(?:optional_)?secret_names:\s*\[(.*?)\]", re.MULTILINE)
VALID_VALUES = {"CHANGE_ME", '""'}
ENCRYPTED = "$ANSIBLE_VAULT;"


def is_variable(name: str) -> bool:
    return name not in NOT_VARIABLES and not name.startswith(PLACEHOLDER_PREFIXES)


def defined(root: Path) -> dict[str, str]:
    """The variables of the example, with their value."""
    text = (root / EXAMPLE).read_text(encoding="utf-8")
    return {name: value for name, value in DEFINITION.findall(text)}


def referenced(root: Path) -> set[str]:
    """The variables referenced outside the example."""
    names: set[str] = set()
    for top in SCANNED:
        for path in sorted((root / top).rglob("*")):
            if not path.is_file() or path.suffix not in SUFFIXES or path == root / EXAMPLE:
                continue
            names.update(NAME.findall(path.read_text(encoding="utf-8")))
    return {name for name in names if is_variable(name)}


def catalog_secrets(root: Path) -> set[str]:
    text = (root / CATALOG).read_text(encoding="utf-8")
    return {
        name
        for group in CATALOG_SECRETS.findall(text)
        for name in re.findall(r'"([A-Z0-9_]+)"', group)
    }


def committed_vaults(root: Path) -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*vault.yml"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [root / line for line in listing.stdout.splitlines() if Path(line).name == "vault.yml"]


def problems(root: Path) -> list[str]:
    found: list[str] = []
    values = defined(root)
    used = referenced(root)
    for name in sorted(used - values.keys()):
        found.append(f"{name} is referenced but missing from {EXAMPLE}")
    for name in sorted(values.keys() - used):
        found.append(f"{name} is in {EXAMPLE} but not referenced in {', '.join(SCANNED)}")
    for name, value in sorted(values.items()):
        if value not in VALID_VALUES:
            found.append(f"{name}: the value must be CHANGE_ME or empty, not {value!r}")
    page = (root / SECRETS_PAGE).read_text(encoding="utf-8")
    for secret in sorted(catalog_secrets(root)):
        if f"`{secret}`" not in page:
            found.append(f"the catalog secret {secret} is not described in {SECRETS_PAGE}")
    for path in committed_vaults(root):
        if not path.read_text(encoding="utf-8").startswith(ENCRYPTED):
            found.append(
                f"{path.relative_to(root)} is committed in clear: encrypt it with ansible-vault"
            )
    return found


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print("usage: check_vault_example.py [ROOT]")
        return 2
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    found = problems(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
