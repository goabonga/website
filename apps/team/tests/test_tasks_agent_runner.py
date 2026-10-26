# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for agent runner task."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from team.models import Conversation, ConversationParticipant, Message
from team.services.llm import ChatResult, ToolCall
from team.tasks.agent_runner import (
    _build_messages,
    _build_skills_context,
    _build_team_context,
    _build_tool_guidelines,
    _cleanup_workspace,
    _filter_tools_by_credentials,
    _format_parent_results,
    _is_credit_error,
    _run_agent,
    _save_message,
    _task_workspace,
    run_agent_task,
)


def _make_task(**kwargs):
    task = MagicMock()
    task.id = kwargs.get("id", uuid4())
    task.team_id = kwargs.get("team_id", uuid4())
    task.agent_id = kwargs.get("agent_id", uuid4())
    task.workflow_id = kwargs.get("workflow_id")
    task.title = kwargs.get("title", "Test task")
    task.description = kwargs.get("description", "Do something")
    task.status = kwargs.get("status", "assigned")
    task.input_data = kwargs.get("input_data", {})
    task.output_data = {}
    task.updated_at = None
    return task


def _make_agent(**kwargs):
    agent = MagicMock()
    agent.id = kwargs.get("id", uuid4())
    agent.name = kwargs.get("name", "TestAgent")
    agent.provider = kwargs.get("provider", "openai")
    agent.model = kwargs.get("model", "gpt-4o")
    agent.system_prompt = kwargs.get("system_prompt", "You are helpful.")
    agent.config = kwargs.get("config", {})
    return agent


def _mock_factory(session):
    factory = MagicMock()
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=False)
    return factory


def _team_agents_result():
    """Mock result for _build_team_context query (Agent.name, Agent.role)."""
    result = MagicMock()
    result.all.return_value = [("DevAgent", "developer"), ("QA Agent", "qa")]
    return result


def _cancel_check(status="in_progress"):
    """Mock result for cancellation check (select(Task.status))."""
    result = MagicMock()
    result.scalar_one.return_value = status
    return result


def _empty_skills_result():
    """Mock result for _build_skills_context query (no skills)."""
    result = MagicMock()
    result.all.return_value = []
    return result


def _skills_result(skills=None):
    """Mock result for _build_skills_context query with skills."""
    result = MagicMock()
    result.all.return_value = skills or []
    return result


class TestBuildMessages:
    def test_from_prompt(self):
        task = _make_task(input_data={"prompt": "Hello"})
        msgs = _build_messages(task)
        assert msgs == [{"role": "user", "content": "Hello"}]

    def test_from_messages(self):
        task = _make_task(input_data={"messages": [{"role": "user", "content": "Hi"}]})
        msgs = _build_messages(task)
        assert msgs == [{"role": "user", "content": "Hi"}]

    def test_fallback_to_title(self):
        task = _make_task(input_data={}, description="", title="Fix bug")
        msgs = _build_messages(task)
        assert msgs == [{"role": "user", "content": "Fix bug"}]

    def test_empty_input_data(self):
        task = _make_task(input_data=None, title="My task", description="")
        msgs = _build_messages(task)
        assert msgs == [{"role": "user", "content": "My task"}]

    def test_prompt_with_parent_results(self):
        task = _make_task(
            input_data={
                "prompt": "Write the report",
                "parent_results": {"step_1": "Research data here"},
            }
        )
        msgs = _build_messages(task)
        assert len(msgs) == 1
        assert "Results from previous workflow steps" in msgs[0]["content"]
        assert "step_1" in msgs[0]["content"]
        assert "Research data here" in msgs[0]["content"]
        assert "Write the report" in msgs[0]["content"]

    def test_messages_with_parent_results(self):
        task = _make_task(
            input_data={
                "messages": [{"role": "user", "content": "Do the work"}],
                "parent_results": {"step_1": "Previous output"},
            }
        )
        msgs = _build_messages(task)
        assert len(msgs) == 2
        assert "Results from previous workflow steps" in msgs[0]["content"]
        assert "Previous output" in msgs[0]["content"]
        assert msgs[1]["content"] == "Do the work"

    def test_empty_parent_results_ignored(self):
        task = _make_task(
            input_data={
                "prompt": "Hello",
                "parent_results": {},
            }
        )
        msgs = _build_messages(task)
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Hello"

    def test_multiple_parent_results(self):
        task = _make_task(
            input_data={
                "prompt": "Summarize",
                "parent_results": {
                    "step_1": "First output",
                    "step_2": "Second output",
                },
            }
        )
        msgs = _build_messages(task)
        assert len(msgs) == 1
        content = msgs[0]["content"]
        assert "step_1" in content
        assert "First output" in content
        assert "step_2" in content
        assert "Second output" in content
        assert "Summarize" in content


class TestFormatParentResults:
    def test_single_step(self):
        result = _format_parent_results({"step_1": "Some output"})
        assert "## Results from previous workflow steps" in result
        assert "### Step: step_1" in result
        assert "Some output" in result

    def test_multiple_steps(self):
        result = _format_parent_results(
            {
                "research": "Research findings",
                "analysis": "Analysis results",
            }
        )
        assert "### Step: research" in result
        assert "Research findings" in result
        assert "### Step: analysis" in result
        assert "Analysis results" in result


class TestSaveMessage:
    def test_adds_message_to_session(self):
        session = MagicMock()
        conv_id = uuid4()
        agent_id = uuid4()

        _save_message(
            session, conv_id, agent_id, "message", {"role": "assistant", "content": "hi"}, "hi"
        )

        session.add.assert_called_once()
        msg = session.add.call_args[0][0]
        assert isinstance(msg, Message)
        assert msg.conversation_id == conv_id
        assert msg.agent_id == agent_id
        assert msg.type == "message"
        assert msg.text == "hi"

    def test_adds_tool_output(self):
        session = MagicMock()
        conv_id = uuid4()

        _save_message(session, conv_id, None, "tool_output", {"role": "tool"}, "result")

        msg = session.add.call_args[0][0]
        assert isinstance(msg, Message)
        assert msg.type == "tool_output"
        assert msg.agent_id is None


class TestBuildTeamContext:
    async def test_returns_agent_listing(self):
        mock_session = AsyncMock()
        result = MagicMock()
        result.all.return_value = [("CEO Agent", "ceo"), ("Dev Agent", "developer")]
        mock_session.execute = AsyncMock(return_value=result)

        ctx = await _build_team_context(mock_session, uuid4())
        assert "ceo" in ctx
        assert "developer" in ctx
        assert "CEO Agent" in ctx
        assert "role:" in ctx

    async def test_returns_empty_string_when_no_agents(self):
        mock_session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        ctx = await _build_team_context(mock_session, uuid4())
        assert ctx == ""


class TestBuildSkillsContext:
    async def test_returns_xml_block_with_skills(self):
        mock_session = AsyncMock()
        result = MagicMock()
        result.all.return_value = [
            ("code-review", "Review code changes."),
            ("deploy", "Deploy to production."),
        ]
        mock_session.execute = AsyncMock(return_value=result)

        ctx = await _build_skills_context(mock_session, uuid4())
        assert "## Agent Skills" in ctx
        assert "<available_skills>" in ctx
        assert "<name>code-review</name>" in ctx
        assert "<description>Review code changes.</description>" in ctx
        assert "<name>deploy</name>" in ctx
        assert "</available_skills>" in ctx

    async def test_returns_empty_string_when_no_skills(self):
        mock_session = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        ctx = await _build_skills_context(mock_session, uuid4())
        assert ctx == ""


class TestBuildToolGuidelines:
    def test_returns_guidelines_for_configured_tools(self):
        result = _build_tool_guidelines(["save_memory", "git_clone", "http_request"])
        assert "## Tool usage guidelines" in result
        assert "save_memory" in result
        assert "git_clone" in result
        # http_request has no guideline entry
        assert "http_request" not in result

    def test_returns_empty_string_when_no_matching_tools(self):
        assert _build_tool_guidelines(["http_request", "postgres_query"]) == ""

    def test_returns_empty_string_for_empty_list(self):
        assert _build_tool_guidelines([]) == ""


class TestFilterToolsByCredentials:
    def test_all_tools_kept_when_github_configured(self):
        tools = ["search_memory", "github_create_issue", "git_clone", "create_task"]
        settings = MagicMock(github_token="ghp_xxx", github_owner="goabonga")
        with patch("team.tasks.agent_runner.get_settings", return_value=settings):
            result = _filter_tools_by_credentials(tools)
        assert result == tools

    def test_github_tools_removed_when_token_missing(self):
        tools = [
            "search_memory",
            "github_create_issue",
            "github_create_pr",
            "git_clone",
            "create_task",
        ]
        settings = MagicMock(github_token="", github_owner="goabonga")
        with patch("team.tasks.agent_runner.get_settings", return_value=settings):
            result = _filter_tools_by_credentials(tools)
        assert result == ["search_memory", "create_task"]

    def test_github_tools_removed_when_owner_missing(self):
        tools = ["github_create_issue", "save_memory"]
        settings = MagicMock(github_token="ghp_xxx", github_owner="")
        with patch("team.tasks.agent_runner.get_settings", return_value=settings):
            result = _filter_tools_by_credentials(tools)
        assert result == ["save_memory"]

    def test_non_github_tools_unaffected(self):
        tools = ["search_memory", "save_memory", "create_task", "http_request"]
        settings = MagicMock(github_token="", github_owner="")
        with patch("team.tasks.agent_runner.get_settings", return_value=settings):
            result = _filter_tools_by_credentials(tools)
        assert result == tools

    def test_empty_tools_list(self):
        settings = MagicMock(github_token="", github_owner="")
        with patch("team.tasks.agent_runner.get_settings", return_value=settings):
            result = _filter_tools_by_credentials([])
        assert result == []


class TestRunAgentSimple:
    async def test_simple_completion(self):
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),  # loop iter 0 + final check
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        assert task.status == "completed"
        assert task.output_data["content"] == "Done!"
        assert "conversation_id" in task.output_data

    async def test_simple_completion_no_team_context(self):
        """Cover the branch where team_context is empty (no active agents)."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        # Empty team agents → team_context will be ""
        empty_team = MagicMock()
        empty_team.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                empty_team,
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),  # loop iter 0 + final check
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ) as mock_chat,
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        # system_prompt should NOT have team context appended
        call_kwargs = mock_chat.call_args[1]
        assert "Team members" not in call_kwargs["system_prompt"]

    async def test_skills_context_injected_in_system_prompt(self):
        """When an agent has active skills, the system prompt contains <available_skills> XML."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _skills_result([("code-review", "Review code changes.")]),
                _cancel_check(),
                _cancel_check(),  # loop iter 0 + final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        mock_tool_service = MagicMock()
        mock_tool_service.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "activate_skill"}}
        ]
        mock_tool_service.close = AsyncMock()

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ) as mock_chat,
            patch("team.tasks.agent_runner.ToolService", return_value=mock_tool_service),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        call_kwargs = mock_chat.call_args[1]
        assert "<available_skills>" in call_kwargs["system_prompt"]
        assert "<name>code-review</name>" in call_kwargs["system_prompt"]
        # activate_skill tool should have been auto-injected
        assert call_kwargs["tools"] is not None

    async def test_task_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "team.tasks.agent_runner.async_session_factory",
            return_value=_mock_factory(mock_session),
        ):
            result = await _run_agent(str(uuid4()))

        assert result["status"] == "skipped"

    async def test_task_not_assigned(self):
        task = _make_task(status="pending")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "team.tasks.agent_runner.async_session_factory",
            return_value=_mock_factory(mock_session),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "skipped"

    async def test_agent_not_found(self):
        task = _make_task()

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[task_result, agent_result])
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.agent_runner.async_session_factory",
            return_value=_mock_factory(mock_session),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "failed"
        assert task.status == "failed"


class TestRunAgentToolCalling:
    async def test_tool_call_loop(self):
        task = _make_task()
        agent = _make_agent(id=task.agent_id, config={"tools": ["search_memory"]})

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),
                _cancel_check(),  # iter 0, iter 1, final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # First call: tool use, second call: end turn
        chat_tool = ChatResult(
            content="",
            tool_calls=[ToolCall(id="call_1", name="search_memory", arguments={"query": "test"})],
            stop_reason="tool_use",
        )
        chat_final = ChatResult(content="Found it!", stop_reason="end_turn")

        mock_tool_service = MagicMock()
        mock_tool_service.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "search_memory"}}
        ]
        mock_tool_service.execute_tool = AsyncMock(return_value={"results": []})
        mock_tool_service.format_tool_result = AsyncMock(
            return_value={"role": "tool", "tool_call_id": "call_1", "content": {"results": []}}
        )
        mock_tool_service.close = AsyncMock()

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=[chat_tool, chat_final],
            ),
            patch("team.tasks.agent_runner.ToolService", return_value=mock_tool_service),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        assert task.output_data["content"] == "Found it!"
        assert "conversation_id" in task.output_data
        mock_tool_service.execute_tool.assert_awaited_once()

    async def test_max_iterations(self):
        task = _make_task()
        agent = _make_agent(
            id=task.agent_id, config={"tools": ["search_memory"], "max_iterations": 2}
        )

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),
                _cancel_check(),  # iter 0, iter 1, final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Always returns tool_use
        chat_tool = ChatResult(
            content="still working",
            tool_calls=[ToolCall(id="call_1", name="search_memory", arguments={"query": "x"})],
            stop_reason="tool_use",
        )

        mock_tool_service = MagicMock()
        mock_tool_service.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "search_memory"}}
        ]
        mock_tool_service.execute_tool = AsyncMock(return_value={"results": []})
        mock_tool_service.format_tool_result = AsyncMock(
            return_value={"role": "tool", "tool_call_id": "call_1", "content": {}}
        )
        mock_tool_service.close = AsyncMock()

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat_tool,
            ),
            patch("team.tasks.agent_runner.ToolService", return_value=mock_tool_service),
        ):
            result = await _run_agent(str(task.id))

        # Still completes (with last content)
        assert result["status"] == "completed"
        assert task.status == "completed"


class TestRunAgentErrors:
    async def test_llm_exception_marks_failed(self):
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),  # iter 0 cancel check, then LLM throws
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Error recovery session
        err_task_result = MagicMock()
        err_task_result.scalar_one_or_none.return_value = task

        err_session = AsyncMock()
        err_session.execute = AsyncMock(return_value=err_task_result)
        err_session.commit = AsyncMock()

        call_count = [0]

        def factory_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_factory(mock_session)
            return _mock_factory(err_session)

        with (
            patch("team.tasks.agent_runner.async_session_factory", side_effect=factory_side_effect),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=Exception("LLM error"),
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "failed"
        assert "LLM error" in result["error"]


class TestAgentState:
    async def test_agent_state_updated(self):
        task = _make_task()
        agent = _make_agent(id=task.agent_id)
        agent_state = MagicMock()
        agent_state.state = "idle"
        agent_state.current_task = ""

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result_mock = MagicMock()
        agent_result_mock.scalar_one_or_none.return_value = agent

        state_result_mock = MagicMock()
        state_result_mock.scalar_one_or_none.return_value = agent_state

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result_mock,
                state_result_mock,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),  # iter 0 + final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
        ):
            await _run_agent(str(task.id))

        # Agent state should be reset to idle after completion
        assert agent_state.state == "idle"
        assert agent_state.current_task == ""


class TestRunAgentWithWorkflow:
    async def test_triggers_advance_workflow(self):
        wf_id = uuid4()
        task = _make_task(workflow_id=wf_id)
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),  # iter 0 + final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
            patch(
                "team.tasks.agent_runner._advance_workflow", new_callable=AsyncMock
            ) as mock_advance,
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        mock_advance.assert_awaited_once_with(mock_session, task)


class TestToolExecutionError:
    async def test_tool_exception_caught(self):
        """When a tool raises, the error is captured and the loop continues."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id, config={"tools": ["search_memory"]})
        agent_state = MagicMock()
        agent_state.state = "idle"
        agent_state.current_task = ""

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = agent_state

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),
                _cancel_check(),  # iter 0, iter 1, final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # First call: tool use, second call: end turn
        chat_tool = ChatResult(
            content="",
            tool_calls=[ToolCall(id="call_1", name="search_memory", arguments={"query": "test"})],
            stop_reason="tool_use",
        )
        chat_final = ChatResult(content="Handled error", stop_reason="end_turn")

        mock_tool_service = MagicMock()
        mock_tool_service.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "search_memory"}}
        ]
        mock_tool_service.execute_tool = AsyncMock(side_effect=RuntimeError("boom"))
        mock_tool_service.format_tool_result = AsyncMock(
            return_value={"role": "tool", "tool_call_id": "call_1", "content": {"error": "boom"}}
        )
        mock_tool_service.close = AsyncMock()

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=[chat_tool, chat_final],
            ),
            patch("team.tasks.agent_runner.ToolService", return_value=mock_tool_service),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"
        # Agent state was set to "executing" during tool loop
        assert agent_state.state == "idle"


class TestErrorRecoveryTaskNotFound:
    async def test_error_recovery_task_not_found(self):
        """When error recovery can't find the task, it still returns failed."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),  # iter 0 cancel check, then LLM throws
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Error recovery session: task not found
        err_result = MagicMock()
        err_result.scalar_one_or_none.return_value = None

        err_session = AsyncMock()
        err_session.execute = AsyncMock(return_value=err_result)
        err_session.commit = AsyncMock()

        call_count = [0]

        def factory_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_factory(mock_session)
            return _mock_factory(err_session)

        with (
            patch("team.tasks.agent_runner.async_session_factory", side_effect=factory_side_effect),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=Exception("LLM error"),
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "failed"
        err_session.commit.assert_not_awaited()


class TestErrorRecoveryFailure:
    async def test_double_exception(self):
        """When error recovery itself fails, it logs and returns failed."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),  # iter 0 cancel check, then LLM throws
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        call_count = [0]

        def factory_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_factory(mock_session)
            # Second call (error recovery) also fails
            factory = MagicMock()
            factory.__aenter__ = AsyncMock(side_effect=RuntimeError("DB down"))
            factory.__aexit__ = AsyncMock(return_value=False)
            return factory

        with (
            patch("team.tasks.agent_runner.async_session_factory", side_effect=factory_side_effect),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=Exception("LLM error"),
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "failed"
        assert "LLM error" in result["error"]


class TestConversationPersistence:
    async def test_conversation_created_on_run(self):
        """Verify Conversation, Participant, and Messages are created."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),  # iter 0 + final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"

        # Collect all objects passed to session.add()
        added_objects = [call[0][0] for call in mock_session.add.call_args_list]
        added_types = [type(obj).__name__ for obj in added_objects]

        assert "Conversation" in added_types
        assert "ConversationParticipant" in added_types
        assert "Message" in added_types

        # Verify Conversation attributes
        conversations = [obj for obj in added_objects if isinstance(obj, Conversation)]
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv.slug == f"task-{task.id}"
        assert conv.team_id == task.team_id
        assert conv.type == "task"
        assert conv.status == "completed"

        # Verify conversation_id in output_data
        assert task.output_data["conversation_id"] == str(conv.id)

        # Verify participant
        participants = [obj for obj in added_objects if isinstance(obj, ConversationParticipant)]
        assert len(participants) == 1
        assert participants[0].agent_id == agent.id
        assert participants[0].role == "member"

        # Verify messages: 1 user + 1 assistant = 2
        message_objs = [obj for obj in added_objects if isinstance(obj, Message)]
        assert len(message_objs) == 2
        assert message_objs[0].type == "message"
        assert message_objs[0].agent_id is None  # user message
        assert message_objs[1].type == "message"
        assert message_objs[1].agent_id == agent.id  # assistant message

    async def test_tool_output_messages_persisted(self):
        """Verify tool output messages are saved with type='tool_output'."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id, config={"tools": ["search_memory"]})

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),
                _cancel_check(),
                _cancel_check(),  # iter 0, iter 1, final
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat_tool = ChatResult(
            content="",
            tool_calls=[ToolCall(id="call_1", name="search_memory", arguments={"query": "test"})],
            stop_reason="tool_use",
        )
        chat_final = ChatResult(content="Found it!", stop_reason="end_turn")

        mock_tool_service = MagicMock()
        mock_tool_service.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "search_memory"}}
        ]
        mock_tool_service.execute_tool = AsyncMock(return_value={"results": []})
        mock_tool_service.format_tool_result = AsyncMock(
            return_value={"role": "tool", "tool_call_id": "call_1", "content": {"results": []}}
        )
        mock_tool_service.close = AsyncMock()

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=[chat_tool, chat_final],
            ),
            patch("team.tasks.agent_runner.ToolService", return_value=mock_tool_service),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "completed"

        added_objects = [call[0][0] for call in mock_session.add.call_args_list]
        message_objs = [obj for obj in added_objects if isinstance(obj, Message)]

        # 1 user + 1 assistant (tool call) + 1 tool_output + 1 assistant (final) = 4
        assert len(message_objs) == 4
        assert message_objs[0].type == "message"  # user
        assert message_objs[1].type == "message"  # assistant (tool call)
        assert message_objs[2].type == "tool_output"  # tool result
        assert message_objs[2].agent_id == agent.id
        assert message_objs[3].type == "message"  # assistant (final)


class TestCancellation:
    async def test_cancelled_during_loop(self):
        """Agent runner detects cancellation at start of loop iteration."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)
        agent_state = MagicMock()
        agent_state.state = "thinking"
        agent_state.current_task = task.title

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = agent_state

        # Cancel check returns "cancelled"
        cancel_check = MagicMock()
        cancel_check.scalar_one.return_value = "cancelled"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                cancel_check,
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.agent_runner.async_session_factory",
            return_value=_mock_factory(mock_session),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "cancelled"
        assert agent_state.state == "idle"
        assert agent_state.current_task == ""

    async def test_cancelled_during_loop_no_agent_state(self):
        """Cancel detected in loop when agent_state is None (covers 140->144)."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None  # No agent state

        cancel_check = MagicMock()
        cancel_check.scalar_one.return_value = "cancelled"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                cancel_check,
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with patch(
            "team.tasks.agent_runner.async_session_factory",
            return_value=_mock_factory(mock_session),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "cancelled"

    async def test_cancelled_before_completion(self):
        """Agent runner detects cancellation just before marking completed."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        # First cancel check (in loop): not cancelled
        loop_cancel = MagicMock()
        loop_cancel.scalar_one.return_value = "in_progress"

        # Final cancel check (before completion): cancelled
        final_cancel = MagicMock()
        final_cancel.scalar_one.return_value = "cancelled"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                loop_cancel,
                final_cancel,
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "cancelled"
        assert task.status != "completed"

    async def test_cancelled_before_completion_with_agent_state(self):
        """Final cancel check with truthy agent_state resets it (covers 251-253)."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)
        agent_state = MagicMock()
        agent_state.state = "thinking"
        agent_state.current_task = task.title

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = agent_state

        # Loop cancel check: not cancelled
        loop_cancel = MagicMock()
        loop_cancel.scalar_one.return_value = "in_progress"

        # Final cancel check: cancelled
        final_cancel = MagicMock()
        final_cancel.scalar_one.return_value = "cancelled"

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                loop_cancel,
                final_cancel,
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        chat = ChatResult(content="Done!", stop_reason="end_turn")

        with (
            patch(
                "team.tasks.agent_runner.async_session_factory",
                return_value=_mock_factory(mock_session),
            ),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                return_value=chat,
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "cancelled"
        assert agent_state.state == "idle"
        assert agent_state.current_task == ""


def _fake_run_async(coro, return_value=None):
    """Close the coroutine to avoid 'was never awaited' warnings."""
    coro.close()
    return return_value


class TestTaskWorkspace:
    def test_task_workspace_returns_path_with_task_id(self, tmp_path):
        with patch("team.tasks.agent_runner.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = _task_workspace("abc-123")
        assert result == tmp_path / "abc-123"

    def test_task_workspace_under_workspace_dir(self, tmp_path):
        with patch("team.tasks.agent_runner.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            result = _task_workspace(str(uuid4()))
        assert str(result).startswith(str(tmp_path))


class TestCleanupWorkspace:
    def test_cleanup_removes_existing_directory(self, tmp_path):
        task_id = str(uuid4())
        ws = tmp_path / task_id
        ws.mkdir()
        (ws / "file.txt").write_text("data")

        with patch("team.tasks.agent_runner.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            _cleanup_workspace(task_id)

        assert not ws.exists()

    def test_cleanup_noop_if_directory_missing(self, tmp_path):
        with patch("team.tasks.agent_runner.get_settings") as m:
            m.return_value.workspace_dir = str(tmp_path)
            _cleanup_workspace(str(uuid4()))  # Should not raise

    def test_cleanup_logs_error_on_failure(self, tmp_path):
        task_id = str(uuid4())
        ws = tmp_path / task_id
        ws.mkdir()

        with (
            patch("team.tasks.agent_runner.get_settings") as m,
            patch("shutil.rmtree", side_effect=OSError("permission denied")),
            patch("team.tasks.agent_runner.logger") as mock_logger,
        ):
            m.return_value.workspace_dir = str(tmp_path)
            _cleanup_workspace(task_id)

        mock_logger.exception.assert_called_once()


class TestIsCreditError:
    def test_detects_credit_balance_too_low(self):
        exc = Exception(
            "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API.'}}"
        )
        assert _is_credit_error(exc) is True

    def test_detects_credit_balance_insufficient(self):
        exc = Exception("Your credit balance is insufficient for this request.")
        assert _is_credit_error(exc) is True

    def test_ignores_unrelated_errors(self):
        assert _is_credit_error(Exception("LLM error")) is False
        assert _is_credit_error(Exception("Connection timeout")) is False
        assert _is_credit_error(RuntimeError("Something broke")) is False


class TestCreditErrorPaused:
    async def test_credit_error_sets_paused(self):
        """When the LLM raises a credit error, the task is set to paused (not failed)."""
        task = _make_task()
        agent = _make_agent(id=task.agent_id)

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task

        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[
                task_result,
                agent_result,
                state_result,
                _team_agents_result(),
                _empty_skills_result(),
                _cancel_check(),  # iter 0 cancel check, then LLM throws
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Error recovery session
        err_task_result = MagicMock()
        err_task_result.scalar_one_or_none.return_value = task

        err_session = AsyncMock()
        err_session.execute = AsyncMock(return_value=err_task_result)
        err_session.commit = AsyncMock()

        call_count = [0]

        def factory_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_factory(mock_session)
            return _mock_factory(err_session)

        credit_error = Exception(
            "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API.'}}"
        )

        with (
            patch("team.tasks.agent_runner.async_session_factory", side_effect=factory_side_effect),
            patch(
                "team.tasks.agent_runner.get_chat_completion",
                new_callable=AsyncMock,
                side_effect=credit_error,
            ),
        ):
            result = await _run_agent(str(task.id))

        assert result["status"] == "paused"
        assert task.status == "paused"
        assert "credit balance" in task.output_data["error"].lower()


class TestRunAgentTask:
    def test_sync_wrapper(self):
        with patch(
            "team.tasks.agent_runner.run_async",
            side_effect=lambda coro: _fake_run_async(
                coro, {"status": "completed", "task_id": "abc"}
            ),
        ):
            result = run_agent_task(str(uuid4()))

        assert result["status"] == "completed"
