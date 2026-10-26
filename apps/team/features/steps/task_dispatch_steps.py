# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the dispatch features: Celery tasks run in-process on the scenario database."""

import json
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

from behave import given, step, then, when
from sqlalchemy import select
from team.celery import celery_app
from team.models import Agent, Task, Team
from team.tasks.auto_orchestrate import auto_orchestrate
from team.tasks.dispatch_tasks import dispatch_tasks
from team.tasks.webhook_tasks import process_webhook_event


def _expand(context, text: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: str(context.vars[m.group(1)]), text)


def _load(context, query):
    async def run():
        async with context.session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    return context.run(run)


def _task_by_title(context, title: str) -> Task:
    return _load(context, select(Task).where(Task.title == title))[0]


@given("the task workers use the database of the scenario")
def step_workers_database(context) -> None:
    for module in ("dispatch_tasks", "auto_orchestrate", "webhook_tasks"):
        patcher = patch(f"team.tasks.{module}.async_session_factory", context.session_factory)
        patcher.start()
        context.add_cleanup(patcher.stop)


@when("the dispatcher runs")
def step_dispatch(context) -> None:
    context.task_result = dispatch_tasks.apply().get()


@when("the dispatcher runs with a batch size of {size:d}")
def step_dispatch_batch(context, size: int) -> None:
    context.task_result = dispatch_tasks.apply(kwargs={"batch_size": size}).get()


@then("the dispatcher result is '{result}'")
def step_dispatch_result(context, result: str) -> None:
    assert context.task_result == json.loads(result), context.task_result


@then('the task titled "{title}" is "{status}" to the agent "{agent}"')
def step_task_assigned(context, title: str, status: str, agent: str) -> None:
    task = _task_by_title(context, title)
    names = {a.id: a.name for a in _load(context, select(Agent))}
    assert (task.status, names.get(task.agent_id)) == (status, agent), (task.status, task.agent_id)


@then('the task titled "{title}" is "{status}" to nobody')
def step_task_unassigned(context, title: str, status: str) -> None:
    task = _task_by_title(context, title)
    assert (task.status, task.agent_id) == (status, None), (task.status, task.agent_id)


@then('the runner received the task "{title}"')
def step_runner_received(context, title: str) -> None:
    context.dispatch.assert_any_call(str(_task_by_title(context, title).id))


@given('the task "{title}" is paused with the error "{error}"')
def step_paused(context, title: str, error: str) -> None:
    task_id = _task_by_title(context, title).id

    async def pause() -> None:
        async with context.session_factory() as session:
            task = await session.get(Task, task_id)
            task.status = "paused"
            task.output_data = {"error": error}
            await session.commit()

    context.run(pause)


@then('the output of the task "{title}" is empty')
def step_output_empty(context, title: str) -> None:
    assert _task_by_title(context, title).output_data == {}


@then('the output of the task "{title}" has the content "{content}"')
def step_output_content(context, title: str, content: str) -> None:
    assert _task_by_title(context, title).output_data["content"] == content


@then('the output of the task "{title}" has the error "{error}"')
def step_output_error(context, title: str, error: str) -> None:
    assert _task_by_title(context, title).output_data["error"] == error


@when('the auto orchestration runs for the team "{slug}"')
def step_orchestrate(context, slug: str) -> None:
    context.task_result = auto_orchestrate.apply(args=[slug]).get()


@then('the orchestration status is "{status}"')
def step_orchestration_status(context, status: str) -> None:
    assert context.task_result["status"] == status, context.task_result


@then('the orchestration is skipped because "{reason}"')
def step_orchestration_reason(context, reason: str) -> None:
    assert context.task_result == {"status": "skipped", "reason": reason}, context.task_result


@then('the team has the task "{title}" with the priority {priority:d} and the role "{role}"')
def step_checkin_task(context, title: str, priority: int, role: str) -> None:
    task = _task_by_title(context, title)
    assert (task.priority, task.input_data["role"]) == (priority, role)
    assert "autonomous check-in" in task.input_data["prompt"]
    assert str(task.id) == context.task_result["task_id"]


@given('the team has the orchestration situation "{situation}"')
def step_situation(context, situation: str) -> None:
    team_id = UUID(context.vars["team_id"])

    async def arrange() -> None:
        async with context.session_factory() as session:
            if situation != "no ceo":
                session.add(Agent(team_id=team_id, name="Chief", role="ceo"))
            if situation == "a disabled orchestration":
                team = await session.get(Team, team_id)
                team.config = {"orchestration": {"enabled": False}}
            if situation == "an active check-in":
                session.add(
                    Task(team_id=team_id, title="Autonomous team check-in", status="in_progress")
                )
            if situation == "a recent check-in":
                team = await session.get(Team, team_id)
                team.config = {"orchestration": {"schedule_minutes": 60}}
                session.add(
                    Task(
                        team_id=team_id,
                        title="Autonomous team check-in",
                        status="completed",
                        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5),
                    )
                )
            await session.commit()

    context.run(arrange)


@step("the webhook event '{payload}' is processed")
def step_webhook(context, payload: str) -> None:
    context.task_result = process_webhook_event.apply(
        args=[json.loads(_expand(context, payload))]
    ).get()


@then('the webhook result is "{status}"')
def step_webhook_result(context, status: str) -> None:
    assert context.task_result["status"] == status, context.task_result


@then('the Celery beat schedule runs "{task}" every {seconds:d} seconds')
def step_beat(context, task: str, seconds: int) -> None:
    entries = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == task]
    assert len(entries) == 1 and entries[0]["schedule"] == float(seconds), entries
