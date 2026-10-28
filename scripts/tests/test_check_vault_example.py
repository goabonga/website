# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The check that the example vault matches the variables the repository uses."""

import importlib.util
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


check = load("check_vault_example")

EXAMPLE = "ansible/examples/inventory/group_vars/all/vault.yml.example"
CATALOG = "ansible/roles/python_app/defaults/main/catalog.yml"
PAGE = "docs/ansible/03-secrets.md"


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A minimal consistent tree: one active and one commented variable."""
    write(
        tmp_path,
        EXAMPLE,
        '---\nvault_a_key: CHANGE_ME\n# vault_b_key: CHANGE_ME\nvault_c_token: ""\n',
    )
    write(
        tmp_path,
        "ansible/examples/inventory/group_vars/all/apps.yml",
        "a: '{{ vault_a_key }}'\nc: '{{ vault_c_token }}'\n",
    )
    write(
        tmp_path, CATALOG, 'x:\n  secret_names: ["API_KEY"]\n  optional_secret_names: ["OTHER"]\n'
    )
    write(tmp_path, PAGE, "| `vault_b_key` | `API_KEY`, `OTHER` |\n")
    return tmp_path


def test_a_consistent_tree_has_no_problem(tree: Path) -> None:
    assert check.problems(tree) == []
    assert check.main([str(tree)]) == 0


def test_a_variable_missing_from_the_example_is_reported(tree: Path) -> None:
    write(tree, "deploy/apps.yml", "x: '{{ vault_new_secret }}'\n")
    assert check.problems(tree) == [
        f"vault_new_secret is referenced but missing from {check.EXAMPLE}"
    ]
    assert check.main([str(tree)]) == 1


def test_an_unreferenced_variable_of_the_example_is_reported(tree: Path) -> None:
    write(tree, EXAMPLE, (tree / EXAMPLE).read_text() + "# vault_dead_one: CHANGE_ME\n")
    (problem,) = check.problems(tree)
    assert problem.startswith("vault_dead_one is in ")


def test_a_variable_referenced_only_by_the_documentation_counts(tree: Path) -> None:
    write(tree, "docs/ansible/roles/x.md", '```\nx: "{{ vault_c_token }}"\n```\n')
    write(tree, "ansible/examples/inventory/group_vars/all/apps.yml", "a: '{{ vault_a_key }}'\n")
    assert check.problems(tree) == []


@pytest.mark.parametrize("value", ["change-me", "s3cr3t-value", "abc123"])
def test_a_value_that_is_not_a_placeholder_is_reported(tree: Path, value: str) -> None:
    write(
        tree,
        EXAMPLE,
        (tree / EXAMPLE).read_text().replace("vault_a_key: CHANGE_ME", f"vault_a_key: {value}"),
    )
    assert check.problems(tree) == [
        f"vault_a_key: the value must be CHANGE_ME or empty, not {value!r}"
    ]


def test_a_catalog_secret_missing_from_the_page_is_reported(tree: Path) -> None:
    write(tree, PAGE, "| `vault_b_key` | `API_KEY` |\n")
    assert check.problems(tree) == [
        f"the catalog secret OTHER is not described in {check.SECRETS_PAGE}"
    ]


def test_the_names_of_the_vault_setting_and_the_placeholders_are_not_variables(tree: Path) -> None:
    write(
        tree,
        "docs/ansible/x.md",
        "vault_password_file, .vault_pass, vault_my_app_secret, vault_alice_password_hash\n",
    )
    assert check.problems(tree) == []


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_a_committed_vault_must_be_encrypted(tree: Path) -> None:
    git(tree, "init", "-q")
    write(tree, "deploy/production/inventory/group_vars/all/vault.yml", "vault_a_key: real\n")
    git(tree, "add", "deploy/production/inventory/group_vars/all/vault.yml")
    assert check.problems(tree) == [
        "deploy/production/inventory/group_vars/all/vault.yml is committed in clear: encrypt it with ansible-vault"
    ]
    write(
        tree,
        "deploy/production/inventory/group_vars/all/vault.yml",
        "$ANSIBLE_VAULT;1.1;AES256\n6162\n",
    )
    assert check.problems(tree) == []


def test_the_usage_is_printed_for_too_many_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["a", "b"]) == 2
    assert "usage" in capsys.readouterr().out


def test_the_repository_is_consistent() -> None:
    """The example vault, the documentation and the roles agree."""
    assert check.problems(ROOT) == []
