# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the agent runner: a scripted model, a temporary workspace and the in-memory database."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from behave import given, step, then
from sqlalchemy import func, select
from team.celery import celery_app
from team.models import (
    Conversation,
    ConversationParticipant,
    ExecutionLog,
    Message,
    Task,
    Workflow,
)
from team.services import ChatResult, OrchestratorService, ToolCall
from team.tasks.agent_runner import _run_agent, run_agent_task


def _uuid(context, name: str) -> UUID:
    return UUID(context.vars[name])


def _load(context, query):
    """Run a read-only query in a session of the scenario and return its scalars."""

    async def run():
        async with context.session_factory() as session:
            return list((await session.execute(query)).scalars().all())

    return context.run(run)


def _task(context) -> Task:
    return _load(context, select(Task).where(Task.id == _uuid(context, "task_id")))[0]


@given("the agent runner is set up")
def step_set_up(context) -> None:
    workspace = tempfile.TemporaryDirectory()
    context.add_cleanup(workspace.cleanup)
    context.workspace = str(Path(workspace.name).resolve())
    context.settings = SimpleNamespace(
        workspace_dir=context.workspace, github_token="", github_owner=""
    )
    context.script = []
    context.model_calls = []

    async def chat(provider, model, system_prompt, messages, tools=None):
        context.model_calls.append(
            {
                "system_prompt": system_prompt,
                "messages": json.loads(json.dumps(messages)),
                "tools": [t["function"]["name"] for t in tools] if tools else None,
            }
        )
        step = context.script.pop(0)
        if step.get("cancel_task"):

            async def cancel() -> None:
                async with context.session_factory() as session:
                    task = await session.get(Task, _uuid(context, "task_id"))
                    task.status = "cancelled"
                    await session.commit()

            await cancel()
        if "error" in step:
            raise RuntimeError(step["error"])
        return step["result"]

    for target, fake in (
        ("async_session_factory", context.session_factory),
        ("get_settings", lambda: context.settings),
        ("get_chat_completion", chat),
    ):
        patcher = patch(f"team.tasks.agent_runner.{target}", fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


@given("GitHub credentials are configured")
def step_github(context) -> None:
    context.settings.github_token = "gh-token"
    context.settings.github_owner = "example"


@given('an assigned task "{title}" with the prompt "{prompt}"')
def step_assigned_task(context, title: str, prompt: str) -> None:
    async def insert() -> str:
        async with context.session_factory() as session:
            task = Task(
                team_id=_uuid(context, "team_id"),
                agent_id=_uuid(context, "agent_id"),
                title=title,
                status="assigned",
                input_data={"prompt": prompt},
            )
            session.add(task)
            await session.commit()
            return str(task.id)

    context.vars["task_id"] = context.run(insert)


@given('a pending task "{title}" of the team')
def step_pending_task(context, title: str) -> None:
    async def insert() -> str:
        async with context.session_factory() as session:
            task = Task(team_id=_uuid(context, "team_id"), title=title)
            session.add(task)
            await session.commit()
            return str(task.id)

    context.vars["task_id"] = context.run(insert)


@step('the model answers "{text}"')
def step_model_answers(context, text: str) -> None:
    context.script.append({"result": ChatResult(content=text)})


def _tool_call(context, tool: str, arguments: str) -> ChatResult:
    call = ToolCall(
        id=f"call_{len(context.script) + 1}", name=tool, arguments=json.loads(arguments)
    )
    return ChatResult(content="", tool_calls=[call], stop_reason="tool_use")


@given("the model asks for the tool \"{tool}\" with the arguments '{arguments}'")
def step_model_asks(context, tool: str, arguments: str) -> None:
    context.script.append({"result": _tool_call(context, tool, arguments)})


@given(
    "the model asks for the tool \"{tool}\" with the arguments '{arguments}' and the task is cancelled meanwhile"
)
def step_model_asks_and_cancel(context, tool: str, arguments: str) -> None:
    context.script.append({"result": _tool_call(context, tool, arguments), "cancel_task": True})


@given('the model fails with "{message}"')
def step_model_fails(context, message: str) -> None:
    context.script.append({"error": message})


@step("the agent runner executes the task")
def step_execute(context) -> None:
    context.run_result = context.run(_run_agent, context.vars["task_id"])


@step("the Celery task run_agent_task is executed for the task")
def step_celery_execute(context) -> None:
    context.run_result = run_agent_task.apply(args=[context.vars["task_id"]]).get()


@then('the run result status is "{status}"')
def step_run_status(context, status: str) -> None:
    assert context.run_result["status"] == status, context.run_result


@then('the Celery result status is "{status}"')
def step_celery_status(context, status: str) -> None:
    assert context.run_result["status"] == status, context.run_result


@then('the task is "{status}"')
def step_task_status(context, status: str) -> None:
    assert _task(context).status == status


@then('the task output content is "{content}"')
def step_task_output(context, content: str) -> None:
    assert _task(context).output_data["content"] == content


@then('the task output error is "{error}"')
def step_task_error(context, error: str) -> None:
    assert _task(context).output_data["error"] == error


@then("the task was sent to the agent runner")
def step_dispatched(context) -> None:
    context.dispatch.assert_called_once_with(context.response.json()["id"])


@then("the task was not sent again")
def step_not_dispatched(context) -> None:
    assert context.dispatch.call_count == 1, context.dispatch.call_args_list


@then('the model received the prompt "{prompt}"')
def step_model_prompt(context, prompt: str) -> None:
    assert context.model_calls[0]["messages"][0]["content"] == prompt


@then("the model was called {count:d} times")
def step_model_calls(context, count: int) -> None:
    assert len(context.model_calls) == count, len(context.model_calls)


@then('the model system prompt contains "{text}"')
def step_system_prompt(context, text: str) -> None:
    assert text in context.model_calls[0]["system_prompt"], context.model_calls[0]["system_prompt"]


@then('the model was offered the tools "{names}"')
def step_offered_tools(context, names: str) -> None:
    assert context.model_calls[0]["tools"] == [n.strip() for n in names.split(",")]


def _tool_message(context) -> dict:
    return next(m for m in context.model_calls[1]["messages"] if m["role"] == "tool")


@then('the second call of the model received a tool message for "{tool}"')
def step_tool_message(context, tool: str) -> None:
    assert "agents" in _tool_message(context)["content"], _tool_message(context)


@then('the second call of the model received the tool error "{error}"')
def step_tool_error(context, error: str) -> None:
    assert _tool_message(context)["content"]["error"] == error


@then(
    'the execution log has {first:d} "{first_event}" entries and {second:d} "{second_event}" entries'
)
def step_log_counts(context, first: int, first_event: str, second: int, second_event: str) -> None:
    async def count(event: str) -> int:
        async with context.session_factory() as session:
            result = await session.execute(
                select(func.count(ExecutionLog.id)).where(ExecutionLog.event_type == event)
            )
            return result.scalar_one()

    assert context.run(count, first_event) == first
    assert context.run(count, second_event) == second


def _conversation(context) -> Conversation:
    slug = f"task-{context.vars['task_id']}"
    return _load(context, select(Conversation).where(Conversation.slug == slug))[0]


@then('the conversation of the task is "{status}" and belongs to the team')
def step_conversation(context, status: str) -> None:
    conversation = _conversation(context)
    assert conversation.status == status and conversation.type == "task"
    assert str(conversation.team_id) == context.vars["team_id"]


@then('the conversation has the messages "{texts}"')
def step_conversation_messages(context, texts: str) -> None:
    conversation = _conversation(context)
    messages = _load(context, select(Message).where(Message.conversation_id == conversation.id))
    assert {m.text for m in messages} == {t.strip() for t in texts.split(",")}


@then("the agent is a participant of the conversation")
def step_participant(context) -> None:
    rows = _load(
        context,
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == _conversation(context).id
        ),
    )
    assert [str(r.agent_id) for r in rows] == [context.vars["agent_id"]]


@given("an active workflow with the steps '{steps}'")
def step_active_workflow(context, steps: str) -> None:
    async def create() -> str:
        async with context.session_factory() as session:
            workflow = Workflow(team_id=_uuid(context, "team_id"), name="Pipeline")
            workflow.steps = json.loads(steps)
            session.add(workflow)
            await session.flush()
            await OrchestratorService(session).start_workflow(workflow)
            await session.commit()
            return str(workflow.id)

    context.vars["workflow_id"] = context.run(create)


def _workflow_task(context, step_id: str) -> Task:
    tasks = _load(context, select(Task).where(Task.workflow_id == _uuid(context, "workflow_id")))
    return next(t for t in tasks if t.input_data.get("step_id") == step_id)


@step('the workflow task for the step "{step_id}" is assigned to the agent')
def step_assign_workflow_task(context, step_id: str) -> None:
    task = _workflow_task(context, step_id)

    async def assign() -> None:
        async with context.session_factory() as session:
            row = await session.get(Task, task.id)
            row.agent_id = _uuid(context, "agent_id")
            row.status = "assigned"
            await session.commit()

    context.run(assign)
    context.vars["task_id"] = str(task.id)


@then(
    'the workflow has a pending task "{title}" that received the result "{result}" of the step "{step_id}"'
)
def step_next_step(context, title: str, result: str, step_id: str) -> None:
    tasks = _load(context, select(Task).where(Task.workflow_id == _uuid(context, "workflow_id")))
    task = next(t for t in tasks if t.title == title)
    assert task.status == "pending" and task.input_data["parent_results"][step_id] == result


@then("no workspace remains for the task")
def step_no_workspace(context) -> None:
    assert not (Path(context.workspace) / context.vars["task_id"]).exists()


@then('the Celery application uses the default queue "{queue}"')
def step_celery_queue(context, queue: str) -> None:
    assert celery_app.conf.task_default_queue == queue


@then('the Celery application includes the task module "{module}"')
def step_celery_include(context, module: str) -> None:
    assert module in celery_app.conf.include


@then('the Celery task "{name}" is registered')
def step_celery_task(context, name: str) -> None:
    celery_app.loader.import_default_modules()
    assert name in celery_app.tasks
