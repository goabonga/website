# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Agent runner — execute assigned tasks via LLM loop with tool calling."""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import team.services.tools  # noqa: F401 — trigger @ToolService.register decorators
from team.celery import celery_app
from team.config import get_settings
from team.database import async_session_factory
from team.models import (
    Agent,
    AgentState,
    Conversation,
    ConversationParticipant,
    ExecutionLog,
    Message,
    Skill,
    Task,
    Workflow,
)
from team.services.llm import ChatResult, get_chat_completion
from team.services.tool_service import ToolService
from team.tasks.utils import run_async

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 10

# Error messages that indicate a temporary billing/credit issue (task should be paused, not failed)
_CREDIT_ERROR_MARKERS = [
    "credit balance is too low",
    "credit balance is insufficient",
]


def _is_credit_error(exc: Exception) -> bool:
    """Return True if the exception indicates insufficient API credits."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _CREDIT_ERROR_MARKERS)


def _task_workspace(task_id: str) -> Path:
    """Return the isolated workspace directory for a given task."""
    return Path(get_settings().workspace_dir).resolve() / task_id


def _cleanup_workspace(task_id: str) -> None:
    """Remove the task workspace directory if it exists."""
    try:
        ws = _task_workspace(task_id)
        if ws.exists():
            shutil.rmtree(ws)
            logger.info(f"Cleaned up task workspace: {ws}")
    except Exception:
        logger.exception(f"Failed to clean up workspace for task {task_id}")


async def _run_agent(task_id: str) -> dict:
    """Execute a task: load agent, LLM loop with tool calls, store result."""
    tool_service = ToolService()

    try:
        async with async_session_factory() as session:
            # 1. Load task
            task_result = await session.execute(select(Task).where(Task.id == UUID(task_id)))
            task = task_result.scalar_one_or_none()
            if not task or task.status != "assigned":
                logger.warning(f"Task {task_id} not found or not assigned")
                return {"status": "skipped"}

            # 2. Load agent
            agent_result = await session.execute(select(Agent).where(Agent.id == task.agent_id))
            agent = agent_result.scalar_one_or_none()
            if not agent:
                task.status = "failed"
                task.output_data = {"error": "Agent not found"}
                task.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()
                return {"status": "failed", "error": "Agent not found"}

            # 3. Mark in_progress, create task workspace, update AgentState
            task.status = "in_progress"
            task.updated_at = datetime.now(UTC).replace(tzinfo=None)

            task_ws = _task_workspace(task_id)
            task_ws.mkdir(parents=True, exist_ok=True)

            state_result = await session.execute(
                select(AgentState).where(AgentState.agent_id == agent.id)
            )
            agent_state = state_result.scalar_one_or_none()
            if agent_state:
                agent_state.state = "thinking"
                agent_state.current_task = task.title
                agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)

            session.add(
                ExecutionLog(
                    team_id=task.team_id,
                    task_id=task.id,
                    agent_id=agent.id,
                    workflow_id=task.workflow_id,
                    event_type="agent.run.started",
                    details={"task_title": task.title},
                )
            )
            await session.commit()

            # 3b. Create conversation for this task run
            conversation = Conversation(
                team_id=task.team_id,
                slug=f"task-{task.id}",
                title=f"Task: {task.title}",
                type="task",
                status="active",
                extra={"task_id": str(task.id), "agent_id": str(agent.id)},
            )
            session.add(conversation)
            await session.flush()
            session.add(
                ConversationParticipant(
                    conversation_id=conversation.id,
                    agent_id=agent.id,
                    role="member",
                )
            )
            await session.commit()

            # 4. Build tool definitions from agent.config
            tool_names = agent.config.get("tools", []) if agent.config else []
            tool_names = _filter_tools_by_credentials(tool_names)

            # 4b. Build team context (available roles)
            team_context = await _build_team_context(session, task.team_id)

            # 4c. Build skills context and auto-inject activate_skill tool
            skills_context = await _build_skills_context(session, agent.id)
            if skills_context and "activate_skill" not in tool_names:
                tool_names = tool_names + ["activate_skill"]

            tools = tool_service.get_tool_definitions(tool_names) if tool_names else None

            # 5. Build initial messages
            messages = _build_messages(task)

            # 5b. Save initial user messages to conversation
            for msg in messages:
                _save_message(
                    session,
                    conversation.id,
                    None,
                    "message",
                    msg,
                    msg.get("content", ""),
                )
            await session.commit()

            # 6. LLM loop
            max_iterations = (
                agent.config.get("max_iterations", DEFAULT_MAX_ITERATIONS)
                if agent.config
                else DEFAULT_MAX_ITERATIONS
            )
            final_content = ""
            iteration = 0

            system_prompt = agent.system_prompt or ""
            if team_context:
                system_prompt = f"{system_prompt}\n\n{team_context}"
            tool_guidelines = _build_tool_guidelines(tool_names)
            if tool_guidelines:
                system_prompt = f"{system_prompt}\n\n{tool_guidelines}"
            if skills_context:
                system_prompt = f"{system_prompt}\n\n{skills_context}"

            for iteration in range(max_iterations):
                # Check for cancellation (column select bypasses identity map)
                cancel_check = await session.execute(select(Task.status).where(Task.id == task.id))
                if cancel_check.scalar_one() == "cancelled":
                    logger.info(f"Task {task_id} cancelled during iteration {iteration}")
                    if agent_state:
                        agent_state.state = "idle"
                        agent_state.current_task = ""
                        agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)
                    conversation.status = "cancelled"
                    conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    session.add(
                        ExecutionLog(
                            team_id=task.team_id,
                            task_id=task.id,
                            agent_id=agent.id,
                            workflow_id=task.workflow_id,
                            event_type="agent.run.cancelled",
                            details={"iteration": iteration},
                        )
                    )
                    await session.commit()
                    return {"status": "cancelled", "task_id": task_id}

                if agent_state:
                    agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)
                    agent_state.state = "thinking"

                chat_result: ChatResult = await get_chat_completion(
                    provider=agent.provider,
                    model=agent.model,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                )

                # Append assistant response
                assistant_msg: dict = {"role": "assistant", "content": chat_result.content}
                if chat_result.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in chat_result.tool_calls
                    ]
                messages.append(assistant_msg)

                # Save assistant message to conversation
                _save_message(
                    session,
                    conversation.id,
                    agent.id,
                    "message",
                    assistant_msg,
                    chat_result.content,
                )
                await session.commit()

                # If no tool calls, we are done
                if chat_result.stop_reason != "tool_use" or not chat_result.tool_calls:
                    final_content = chat_result.content
                    break

                # Execute each tool call
                if agent_state:
                    agent_state.state = "executing"

                context = {
                    "db": session,
                    "team_id": task.team_id,
                    "agent_id": agent.id,
                    "workflow_id": task.workflow_id,
                    "tool_service": tool_service,
                    "agent_config": agent.config or {},
                    "workspace_dir": str(task_ws),
                }

                for tc in chat_result.tool_calls:
                    try:
                        tool_result = await tool_service.execute_tool(
                            tc.name, tc.arguments, context
                        )
                    except Exception as e:
                        tool_result = {"error": str(e)}

                    tool_result_msg = await tool_service.format_tool_result(tc.id, tool_result)
                    messages.append(tool_result_msg)

                    # Save tool output message to conversation
                    _save_message(
                        session,
                        conversation.id,
                        agent.id,
                        "tool_output",
                        tool_result_msg,
                        str(tool_result),
                    )

                    session.add(
                        ExecutionLog(
                            team_id=task.team_id,
                            task_id=task.id,
                            agent_id=agent.id,
                            event_type="agent.tool.executed",
                            details={"tool": tc.name, "iteration": iteration},
                        )
                    )
                await session.commit()
            else:
                final_content = chat_result.content
                logger.warning(f"Task {task_id} hit max iterations ({max_iterations})")

            # 7. Final cancellation check before marking completed
            final_cancel = await session.execute(select(Task.status).where(Task.id == task.id))
            if final_cancel.scalar_one() == "cancelled":
                logger.info(f"Task {task_id} cancelled just before completion")
                if agent_state:
                    agent_state.state = "idle"
                    agent_state.current_task = ""
                    agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)
                conversation.status = "cancelled"
                conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
                session.add(
                    ExecutionLog(
                        team_id=task.team_id,
                        task_id=task.id,
                        agent_id=agent.id,
                        workflow_id=task.workflow_id,
                        event_type="agent.run.cancelled",
                        details={"iteration": iteration + 1, "phase": "pre_completion"},
                    )
                )
                await session.commit()
                return {"status": "cancelled", "task_id": task_id}

            # 8. Store result, mark completed
            task.status = "completed"
            task.output_data = {
                "content": final_content,
                "conversation_id": str(conversation.id),
            }
            task.updated_at = datetime.now(UTC).replace(tzinfo=None)

            # Mark conversation as completed
            conversation.status = "completed"
            conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)

            if agent_state:
                agent_state.state = "idle"
                agent_state.current_task = ""
                agent_state.last_heartbeat = datetime.now(UTC).replace(tzinfo=None)

            session.add(
                ExecutionLog(
                    team_id=task.team_id,
                    task_id=task.id,
                    agent_id=agent.id,
                    workflow_id=task.workflow_id,
                    event_type="agent.run.completed",
                    details={"iterations": iteration + 1},
                )
            )
            await session.commit()

            # 8. Trigger orchestrator for workflow progression
            if task.workflow_id:
                await _advance_workflow(session, task)

            return {"status": "completed", "task_id": task_id}

    except Exception as e:
        is_credit = _is_credit_error(e)
        new_status = "paused" if is_credit else "failed"
        if is_credit:
            logger.warning(f"Task {task_id} paused: insufficient API credits")
        else:
            logger.exception(f"Agent runner failed for task {task_id}")
        try:
            async with async_session_factory() as session:
                err_result = await session.execute(select(Task).where(Task.id == UUID(task_id)))
                task = err_result.scalar_one_or_none()
                if task:
                    task.status = new_status
                    task.output_data = {"error": str(e)}
                    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
                    await session.commit()
        except Exception:
            logger.exception(f"Failed to mark task {task_id} as {new_status}")
        return {"status": new_status, "error": str(e)}
    finally:
        await tool_service.close()
        _cleanup_workspace(task_id)


async def _build_team_context(session: AsyncSession, team_id) -> str:
    """Build a context string listing available team agents and their roles."""
    result = await session.execute(
        select(Agent.name, Agent.role)
        .where(Agent.team_id == team_id, Agent.is_active.is_(True))
        .order_by(Agent.role)
    )
    agents = result.all()
    if not agents:
        return ""

    lines = ["## Team members (use these exact role values when creating tasks)"]
    for name, role in agents:
        lines.append(f"- **{name}** → role: `{role}`")
    return "\n".join(lines)


async def _build_skills_context(session: AsyncSession, agent_id) -> str:
    """Build the <available_skills> XML block for the system prompt.

    Only loads name + description (progressive disclosure).
    Full content is loaded by the activate_skill tool at runtime.
    """
    result = await session.execute(
        select(Skill.name, Skill.description)
        .where(Skill.agent_id == agent_id, Skill.is_active.is_(True))
        .order_by(Skill.name)
    )
    skills = result.all()
    if not skills:
        return ""

    lines = ["<available_skills>"]
    for name, description in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{name}</name>")
        lines.append(f"    <description>{description}</description>")
        lines.append("  </skill>")
    lines.append("</available_skills>")

    preamble = (
        "## Agent Skills\n\n"
        "You have access to the following skills. When a task matches a skill's description, "
        "activate it using the `activate_skill` tool to load its full instructions. "
        "Only activate skills that are relevant to the current task.\n\n"
    )

    return preamble + "\n".join(lines)


TOOL_GUIDELINES = {
    "save_memory": "Use save_memory to persist important findings, decisions, and context for future reference. Always save key outcomes before finishing.",
    "search_memory": "Use search_memory FIRST to recall previous decisions, context, and team knowledge before starting work.",
    "update_memory": "Use update_memory to correct or update an existing memory entry (by ID from search_memory results).",
    "delete_memory": "Use delete_memory to remove outdated or incorrect memory entries (by ID from search_memory results).",
    "git_clone": "Use git_clone to clone repositories before making code changes.",
    "git_create_branch": "Use git_create_branch to create a feature branch before making changes. Never commit directly to main.",
    "git_diff": "Use git_diff to review your changes before committing.",
    "git_commit_push": "Use git_commit_push to commit and push your code changes after making modifications.",
    "github_create_pr": "Use github_create_pr to submit pull requests for code review. Always create a PR when you have committed code changes.",
    "github_create_issue": "Use github_create_issue to track bugs, features, and tasks on GitHub. Create issues for any problem found or feature proposed.",
    "github_get_issue": "Use github_get_issue to read an issue's details (title, body, state, labels, comments) before acting on it.",
    "github_update_issue": "Use github_update_issue to edit or close GitHub issues.",
    "github_get_pr": "Use github_get_pr to read a PR's details (title, body, state, branches, merge status) before reviewing or updating it.",
    "github_update_pr": "Use github_update_pr to edit or close pull requests.",
    "github_comment": "Use github_comment to add comments to existing issues or PRs with status updates or review feedback.",
    "github_list_comments": "Use github_list_comments to read all comments on an issue or PR before responding.",
    "github_list_review_comments": "Use github_list_review_comments to read inline code review comments on a PR (file path, line, diff hunk).",
    "github_update_comment": "Use github_update_comment to edit an existing comment.",
    "github_delete_comment": "Use github_delete_comment to remove an outdated or incorrect comment.",
    "github_list_runs": "Use github_list_runs to check CI/CD pipeline status after pushing code.",
    "github_get_run_logs": "Use github_get_run_logs to diagnose CI failures by reading workflow logs.",
    "create_task": "Use create_task to delegate work to other team members by role.",
    "dir_mkdir": "Use dir_mkdir to create directories in the workspace before writing files into them.",
    "dir_rmdir": "Use dir_rmdir to remove directories. Use recursive=true for non-empty directories.",
    "dir_list": "Use dir_list to explore workspace directory contents before reading or modifying files.",
    "activate_skill": "Use activate_skill to load full instructions for a skill when a task matches one of your available skills. Read the returned instructions carefully before proceeding.",
}

# Tools that require GitHub credentials (token + owner)
_GITHUB_TOOLS = {
    "git_clone",
    "git_create_branch",
    "git_diff",
    "git_commit_push",
    "github_create_issue",
    "github_get_issue",
    "github_create_pr",
    "github_get_pr",
    "github_comment",
    "github_update_issue",
    "github_update_pr",
    "github_list_comments",
    "github_list_review_comments",
    "github_update_comment",
    "github_delete_comment",
    "github_list_runs",
    "github_get_run_logs",
}


def _filter_tools_by_credentials(tool_names: list[str]) -> list[str]:
    """Remove tools whose credentials are missing so the LLM never sees them.

    Returns the filtered list. Logs a warning for each removed tool.
    """
    settings = get_settings()
    has_github = bool(settings.github_token and settings.github_owner)

    if has_github:
        return tool_names

    filtered: list[str] = []
    for name in tool_names:
        if name in _GITHUB_TOOLS:
            logger.warning("Tool %s disabled — GITHUB_TOKEN or GITHUB_OWNER not configured", name)
        else:
            filtered.append(name)
    return filtered


def _build_tool_guidelines(tool_names: list[str]) -> str:
    """Build tool usage guidelines based on agent's configured tools."""
    lines = []
    for name in tool_names:
        if name in TOOL_GUIDELINES:
            lines.append(f"- {TOOL_GUIDELINES[name]}")
    if not lines:
        return ""
    return (
        "## Tool usage guidelines\n\nYou MUST proactively use the tools listed below as part of your workflow. Do not skip tool usage when it is relevant to the task.\n\n"
        + "\n".join(lines)
    )


def _format_parent_results(parent_results: dict[str, str]) -> str:
    """Format parent step results into a context block for the LLM."""
    lines = ["## Results from previous workflow steps\n"]
    for step_id, content in parent_results.items():
        lines.append(f"### Step: {step_id}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _build_messages(task: Task) -> list[dict]:
    """Build initial message list from task input_data."""
    parent_results = (task.input_data or {}).get("parent_results")
    context_prefix = _format_parent_results(parent_results) if parent_results else ""

    if task.input_data and "messages" in task.input_data:
        messages = list(task.input_data["messages"])
        if context_prefix:
            messages.insert(0, {"role": "user", "content": context_prefix})
        return messages

    prompt = (
        task.input_data.get("prompt", task.description or task.title)
        if task.input_data
        else (task.description or task.title)
    )

    if context_prefix:
        prompt = f"{context_prefix}\n---\n\n{prompt}"

    return [{"role": "user", "content": prompt}]


def _save_message(
    session: AsyncSession,
    conversation_id: UUID,
    agent_id: UUID | None,
    msg_type: str,
    content: dict,
    text: str,
) -> None:
    """Add a Message to the session (not yet committed)."""
    session.add(
        Message(
            conversation_id=conversation_id,
            agent_id=agent_id,
            type=msg_type,
            content=content,
            text=text,
        )
    )


async def _advance_workflow(session: AsyncSession, completed_task: Task) -> None:
    """Check if dependent workflow steps can now be started."""
    wf_result = await session.execute(
        select(Workflow).where(Workflow.id == completed_task.workflow_id)
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow or workflow.status != "active":
        return

    steps = workflow.steps
    if not isinstance(steps, list):
        return

    # Get all tasks for this workflow
    tasks_result = await session.execute(select(Task).where(Task.workflow_id == workflow.id))
    all_tasks = list(tasks_result.scalars().all())

    # Build step_id -> status mapping and collect outputs from completed steps
    completed_steps: set[str] = set()
    in_flight_steps: set[str] = set()
    cancelled_steps: set[str] = set()
    step_outputs: dict[str, str] = {}
    for t in all_tasks:
        step_id = (t.input_data or {}).get("step_id")
        if not step_id:
            continue
        if t.status == "completed":
            completed_steps.add(step_id)
            output_content = (t.output_data or {}).get("content", "")
            if output_content:
                step_outputs[step_id] = output_content
        elif t.status in ("pending", "assigned", "in_progress", "paused"):
            in_flight_steps.add(step_id)
        elif t.status == "cancelled":
            cancelled_steps.add(step_id)

    # Find steps whose dependencies are all met and not yet started
    new_tasks_created = 0
    for step in steps:
        step_id = step["id"]
        if step_id in completed_steps or step_id in in_flight_steps or step_id in cancelled_steps:
            continue

        depends_on = step.get("depends_on", [])
        if all(dep in completed_steps for dep in depends_on):
            parent_results = {dep: step_outputs[dep] for dep in depends_on if dep in step_outputs}
            input_data = {
                **step.get("input_template", {}),
                "step_id": step_id,
                "role": step.get("role"),
            }
            if parent_results:
                input_data["parent_results"] = parent_results

            new_task = Task(
                team_id=workflow.team_id,
                workflow_id=workflow.id,
                title=step.get("name", step_id),
                description=step.get("description", ""),
                input_data=input_data,
                priority=step.get("priority", 0),
            )
            session.add(new_task)
            new_tasks_created += 1
            logger.info(f"Created task for workflow step {step_id}")

    # Check if all steps are now completed
    all_step_ids = {s["id"] for s in steps}
    if completed_steps >= all_step_ids:
        workflow.status = "completed"
        workflow.updated_at = datetime.now(UTC).replace(tzinfo=None)
        session.add(
            ExecutionLog(
                team_id=workflow.team_id,
                workflow_id=workflow.id,
                event_type="workflow.completed",
                details={"steps_count": len(steps)},
            )
        )
        logger.info(f"Workflow {workflow.id} completed")

    if new_tasks_created > 0 or workflow.status == "completed":
        await session.commit()


@celery_app.task(
    name="team.tasks.agent_runner.run_agent_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_agent_task(self, task_id: str) -> dict:
    """Run an agent on an assigned task.

    Triggered by dispatch_tasks after task assignment.
    """
    logger.info(f"Running agent for task {task_id}")
    result = run_async(_run_agent(task_id))
    logger.info(f"Agent runner result for task {task_id}: {result.get('status')}")
    return result
