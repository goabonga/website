# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the tasks feature: direct access to the database and the orchestrator."""

from datetime import UTC, datetime
from uuid import UUID

from behave import given, step, then, when
from sqlalchemy import func, select
from team.models import AgentState, ExecutionLog, Task, Workflow
from team.services import OrchestratorService


def _uuid(context, name: str) -> UUID:
    return UUID(context.vars[name])


@given('a task "{title}" of the team with the status "{status}"')
def step_task_with_status(context, title: str, status: str) -> None:
    async def insert() -> str:
        async with context.session_factory() as session:
            task = Task(team_id=_uuid(context, "team_id"), title=title, status=status)
            session.add(task)
            await session.commit()
            return str(task.id)

    context.vars["task_id"] = context.run(insert)


@given('a task "{title}" of the team with the priority {priority:d}')
def step_task_with_priority(context, title: str, priority: int) -> None:
    async def insert() -> str:
        async with context.session_factory() as session:
            task = Task(team_id=_uuid(context, "team_id"), title=title, priority=priority)
            session.add(task)
            await session.commit()
            return str(task.id)

    context.vars["task_id"] = context.run(insert)


@given('the agent is "{state}" the task "{title}"')
def step_agent_state(context, state: str, title: str) -> None:
    async def insert() -> None:
        async with context.session_factory() as session:
            session.add(
                AgentState(
                    agent_id=_uuid(context, "agent_id"),
                    conversation_id=_uuid(context, "conversation_id"),
                    state=state,
                    current_task=title,
                    last_heartbeat=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.commit()

    context.run(insert)


@then('the agent state is "{state}" without a current task')
def step_agent_state_is(context, state: str) -> None:
    async def load() -> tuple[str, str]:
        async with context.session_factory() as session:
            result = await session.execute(
                select(AgentState).where(AgentState.agent_id == _uuid(context, "agent_id"))
            )
            row = result.scalar_one()
            return row.state, row.current_task

    assert context.run(load) == (state, "")


@then('{count:d} "{event}" execution log entries exist')
def step_logs(context, count: int, event: str) -> None:
    async def total() -> int:
        async with context.session_factory() as session:
            result = await session.execute(
                select(func.count(ExecutionLog.id)).where(ExecutionLog.event_type == event)
            )
            return result.scalar_one()

    assert context.run(total) == count


@when("the orchestrator lists the pending tasks of the team")
def step_pending(context) -> None:
    async def pending() -> list[str]:
        async with context.session_factory() as session:
            tasks = await OrchestratorService(session).get_pending_tasks(_uuid(context, "team_id"))
            return [task.title for task in tasks]

    context.service_result = context.run(pending)


@then('the orchestrator returned the tasks "{titles}"')
def step_returned(context, titles: str) -> None:
    assert context.service_result == [t.strip() for t in titles.split(",")], context.service_result


@when("the orchestrator assigns the task to the agent")
def step_assign(context) -> None:
    async def assign() -> None:
        async with context.session_factory() as session:
            task = await session.get(Task, _uuid(context, "task_id"))
            await OrchestratorService(session).assign_task(task, _uuid(context, "agent_id"))
            await session.commit()

    context.run(assign)


@then('the task has the status "{status}" and belongs to the agent')
def step_assigned(context, status: str) -> None:
    async def load() -> tuple[str, UUID]:
        async with context.session_factory() as session:
            task = await session.get(Task, _uuid(context, "task_id"))
            return task.status, task.agent_id

    assert context.run(load) == (status, _uuid(context, "agent_id"))


@step("the workflow has the steps '{steps}'")
def step_workflow_steps(context, steps: str) -> None:
    import json

    async def update() -> None:
        async with context.session_factory() as session:
            workflow = await session.get(Workflow, _uuid(context, "workflow_id"))
            workflow.steps = json.loads(steps)
            await session.commit()

    context.run(update)


@when("the orchestrator starts the workflow")
def step_start(context) -> None:
    async def start() -> list[str]:
        async with context.session_factory() as session:
            workflow = await session.get(Workflow, _uuid(context, "workflow_id"))
            tasks = await OrchestratorService(session).start_workflow(workflow)
            await session.commit()
            return [task.title for task in tasks]

    context.service_result = context.run(start)


@then('the orchestrator created the tasks "{titles}"')
def step_created(context, titles: str) -> None:
    assert context.service_result == [t.strip() for t in titles.split(",")], context.service_result


@then('the workflow is "{status}"')
def step_workflow_status(context, status: str) -> None:
    async def load() -> str:
        async with context.session_factory() as session:
            return (await session.get(Workflow, _uuid(context, "workflow_id"))).status

    assert context.run(load) == status
