# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the maintenance features: logs, workspaces and memory summaries."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from behave import given, then, when
from sqlalchemy import select
from team.models import ExecutionLog, MemoryEntry, Task
from team.tasks.cleanup_tasks import cleanup_old_logs, cleanup_stale_workspaces
from team.tasks.memory_tasks import summarize_memory


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load(context, query):
    async def run():
        async with context.session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    return context.run(run)


def _patch(context, target: str, value) -> None:
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("the maintenance jobs use the database of the scenario")
def step_database(context) -> None:
    workspace = tempfile.TemporaryDirectory()
    context.add_cleanup(workspace.cleanup)
    context.workspace = Path(workspace.name).resolve()
    _patch(context, "team.tasks.cleanup_tasks.async_session_factory", context.session_factory)
    _patch(context, "team.tasks.memory_tasks.async_session_factory", context.session_factory)
    _patch(
        context,
        "team.tasks.cleanup_tasks.get_settings",
        lambda: SimpleNamespace(workspace_dir=str(context.workspace)),
    )
    context.llm_inputs = []


@given("an execution log entry of {old:d} days ago and one of {recent:d} days ago")
def step_logs(context, old: int, recent: int) -> None:
    async def insert() -> None:
        async with context.session_factory() as session:
            for days in (old, recent):
                session.add(
                    ExecutionLog(
                        team_id=UUID(context.vars["team_id"]),
                        event_type="task.assigned",
                        created_at=_now() - timedelta(days=days),
                    )
                )
            await session.commit()

    context.run(insert)


@when("the log cleanup runs")
def step_cleanup_logs(context) -> None:
    context.task_result = cleanup_old_logs.apply().get()


@when("the log cleanup runs for entries older than {days:d} days")
def step_cleanup_logs_days(context, days: int) -> None:
    context.task_result = cleanup_old_logs.apply(kwargs={"days_old": days}).get()


@then("the maintenance result is '{result}'")
def step_result(context, result: str) -> None:
    assert context.task_result == json.loads(result), context.task_result


@then("{count:d} execution log entries remain")
def step_logs_remain(context, count: int) -> None:
    assert len(_load(context, select(ExecutionLog))) == count


@given('a workspace for a "{status}" task')
def step_task_workspace(context, status: str) -> None:
    async def insert() -> str:
        async with context.session_factory() as session:
            task = Task(team_id=UUID(context.vars["team_id"]), title="t", status=status)
            session.add(task)
            await session.commit()
            return str(task.id)

    task_id = context.run(insert)
    (context.workspace / task_id).mkdir()


@given("a workspace for an unknown task")
def step_unknown_workspace(context) -> None:
    (context.workspace / str(uuid4())).mkdir()


@given("a workspace that is not named after a task")
def step_other_workspace(context) -> None:
    (context.workspace / "scratch").mkdir()


@when("the workspace cleanup runs")
def step_cleanup_workspaces(context) -> None:
    context.task_result = cleanup_stale_workspaces.apply().get()


@then("no task workspace remains")
def step_no_workspace(context) -> None:
    assert list(context.workspace.iterdir()) == []


@then("{count:d} workspaces remain")
def step_workspaces_remain(context, count: int) -> None:
    assert len(list(context.workspace.iterdir())) == count


def _memory(context, content: str, hours: int, extra: dict) -> None:
    async def insert() -> None:
        async with context.session_factory() as session:
            session.add(
                MemoryEntry(
                    team_id=UUID(context.vars["team_id"]),
                    content=content,
                    extra=extra,
                    embedding=[0.0],
                    created_at=_now() - timedelta(hours=hours),
                )
            )
            await session.commit()

    context.run(insert)


@given('a memory entry "{content}" of {hours:d} hours ago')
def step_memory(context, content: str, hours: int) -> None:
    _memory(context, content, hours, {})


@given('a summary memory entry "{content}" of {hours:d} hours ago')
def step_summary_memory(context, content: str, hours: int) -> None:
    _memory(context, content, hours, {"is_summary": True})


@given("a language model key is configured")
def step_key(context) -> None:
    _patch(
        context,
        "team.tasks.memory_tasks.settings",
        SimpleNamespace(openai_api_key="key", anthropic_api_key=""),
    )


@given('the language model summarizes as "{summary}"')
def step_model_summary(context, summary: str) -> None:
    step_key(context)

    async def complete(provider, model, system_prompt, user_message):
        context.llm_inputs.append(user_message)
        return summary

    _patch(context, "team.tasks.memory_tasks.get_completion", AsyncMock(side_effect=complete))
    _patch(context, "team.tasks.memory_tasks.generate_embedding", AsyncMock(return_value=[0.0]))


@given("the language model fails")
def step_model_fails(context) -> None:
    step_key(context)
    _patch(
        context,
        "team.tasks.memory_tasks.get_completion",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )
    _patch(context, "team.tasks.memory_tasks.generate_embedding", AsyncMock(return_value=[0.0]))


@given("no language model key is configured")
def step_no_key(context) -> None:
    _patch(
        context,
        "team.tasks.memory_tasks.settings",
        SimpleNamespace(openai_api_key="", anthropic_api_key=""),
    )


@when("the memory summarization runs")
def step_summarize(context) -> None:
    context.task_result = summarize_memory.apply().get()


@then('the team memory holds the contents "{contents}"')
def step_memory_contents(context, contents: str) -> None:
    held = sorted(e.content for e in _load(context, select(MemoryEntry)))
    assert held == sorted(c.strip() for c in contents.split(",")), held


@then("the summary entry records {count:d} source entries")
def step_summary_sources(context, count: int) -> None:
    summaries = [e for e in _load(context, select(MemoryEntry)) if e.extra.get("is_summary")]
    assert [e.extra["source_count"] for e in summaries] == [count]


@then('the language model received "{first}" and "{second}"')
def step_model_input(context, first: str, second: str) -> None:
    assert context.llm_inputs == [f"{first}\n---\n{second}"], context.llm_inputs
