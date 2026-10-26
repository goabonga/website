# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace tools: a temporary workspace, a local git remote and a fake database."""

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import git
from behave import given, step, then


def _expand(context, text: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: str(context.vars[m.group(1)]), text)


def _field(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


@given("an empty workspace")
def step_workspace(context) -> None:
    directory = tempfile.TemporaryDirectory()
    context.add_cleanup(directory.cleanup)
    context.workspace = str(Path(directory.name).resolve())


@step("the agent runs the tool \"{name}\" with '{params}' in the workspace")
def step_run_in_workspace(context, name: str, params: str) -> None:
    context.tool_result = context.run_tool(
        name, json.loads(_expand(context, params)), workspace_dir=context.workspace
    )


@given('a file "{path}" of {size:d} bytes in the workspace')
def step_big_file(context, path: str, size: int) -> None:
    (Path(context.workspace) / path).write_text("x" * size)


@then('the workspace contains the file "{path}"')
def step_has_file(context, path: str) -> None:
    assert (Path(context.workspace) / path).is_file()


@then('the workspace does not contain the file "{path}"')
def step_has_no_file(context, path: str) -> None:
    assert not (Path(context.workspace) / path).exists()


@given('a git repository "{name}" in the workspace with a pushed file "{filename}"')
def step_git_repository(context, name: str, filename: str) -> None:
    remote_dir = tempfile.TemporaryDirectory()
    context.add_cleanup(remote_dir.cleanup)
    context.remote_path = Path(remote_dir.name) / "remote.git"
    git.Repo.init(context.remote_path, bare=True, initial_branch="main")

    path = Path(context.workspace) / name
    repo = git.Repo.init(path, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Agent")
        config.set_value("user", "email", "agent@example.com")
    (path / filename).write_text("first")
    repo.git.add("-A")
    repo.index.commit("Initial commit")
    repo.create_remote("origin", str(context.remote_path))
    repo.git.push("-u", "origin", "main")


@then('the tool result field "{field}" contains "{text}"')
def step_result_contains(context, field: str, text: str) -> None:
    assert text in str(_field(context.tool_result, field)), context.tool_result


@then('the remote repository has {count:d} commits on "{branch}"')
def step_remote_commits(context, count: int, branch: str) -> None:
    remote = git.Repo(context.remote_path)
    assert len(list(remote.iter_commits(branch))) == count


@given("the database answers the rows '{rows}'")
def step_database_rows(context, rows: str) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.fetch = AsyncMock(return_value=json.loads(rows))
            self.close = AsyncMock()

    context.fake_connection = FakeConnection()
    context.connect = AsyncMock(return_value=context.fake_connection)
    patcher = patch("team.services.tools.postgres_query.asyncpg.connect", context.connect)
    patcher.start()
    context.add_cleanup(patcher.stop)


@then('the database received the connection string "{dsn}"')
def step_database_dsn(context, dsn: str) -> None:
    context.connect.assert_awaited_once_with(dsn)
    context.fake_connection.close.assert_awaited_once()
