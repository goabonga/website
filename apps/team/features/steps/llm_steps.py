# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the LLM feature: fake OpenAI and Anthropic clients."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from behave import given, then, when
from team.services import ToolService, get_chat_completion, get_completion


class FakeProvider:
    """Plays an SDK client: records the request and answers with a scripted response."""

    def __init__(self, response) -> None:
        self.create = AsyncMock(return_value=response)
        self.close = AsyncMock()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.messages = SimpleNamespace(create=self.create)

    @property
    def request(self) -> dict:
        return self.create.await_args.kwargs


def _install(context, target: str, response) -> None:
    context.provider = FakeProvider(response)
    patcher = patch(target, return_value=context.provider)
    patcher.start()
    context.add_cleanup(patcher.stop)
    settings = SimpleNamespace(openai_api_key="openai-key", anthropic_api_key="anthropic-key")
    settings_patcher = patch("team.services.llm.settings", settings)
    settings_patcher.start()
    context.add_cleanup(settings_patcher.stop)


def _openai_response(content: str | None, finish: str, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)])


@given('the OpenAI API answers "{content}" and finishes with "{finish}"')
def step_openai_text(context, content: str, finish: str) -> None:
    _install(context, "team.services.llm.openai.AsyncOpenAI", _openai_response(content, finish))


@given("the OpenAI API answers with a call to \"{tool}\" with the arguments '{arguments}'")
def step_openai_tool(context, tool: str, arguments: str) -> None:
    call = SimpleNamespace(id="call_1", function=SimpleNamespace(name=tool, arguments=arguments))
    _install(
        context,
        "team.services.llm.openai.AsyncOpenAI",
        _openai_response(None, "tool_calls", [call]),
    )


@given('the Anthropic API answers "{text}" and stops with "{reason}"')
def step_anthropic_text(context, text: str, reason: str) -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason=reason
    )
    _install(context, "team.services.llm.anthropic.AsyncAnthropic", response)


@given("the Anthropic API answers with a tool use \"{tool}\" with the input '{arguments}'")
def step_anthropic_tool(context, tool: str, arguments: str) -> None:
    block = SimpleNamespace(type="tool_use", id="toolu_1", name=tool, input=json.loads(arguments))
    response = SimpleNamespace(content=[block], stop_reason="tool_use")
    _install(context, "team.services.llm.anthropic.AsyncAnthropic", response)


@given("no API key is configured")
def step_no_keys(context) -> None:
    settings = SimpleNamespace(openai_api_key="", anthropic_api_key="")
    patcher = patch("team.services.llm.settings", settings)
    patcher.start()
    context.add_cleanup(patcher.stop)


def _request(context, provider: str, model: str, messages: list[dict], tools=None) -> None:
    async def call():
        try:
            return await get_chat_completion(
                provider, model, "You are helpful.", messages, tools=tools
            )
        except ValueError as error:
            return error

    outcome = context.run(call)
    if isinstance(outcome, ValueError):
        context.error = str(outcome)
    else:
        context.chat_result = outcome


@when(
    'a chat completion is requested from "{provider}" with the model "{model}" and the message "{text}"'
)
def step_chat(context, provider: str, model: str, text: str) -> None:
    _request(context, provider, model, [{"role": "user", "content": text}])


@when(
    'a chat completion with the tools "{tools}" is requested from "{provider}" with the model "{model}" and the message "{text}"'
)
def step_chat_tools(context, tools: str, provider: str, model: str, text: str) -> None:
    definitions = ToolService().get_tool_definitions([t.strip() for t in tools.split(",")])
    _request(context, provider, model, [{"role": "user", "content": text}], definitions)


@when(
    'a chat completion is requested from "{provider}" after a tool call "{call_id}" to "{tool}" that returned \'{result}\''
)
def step_chat_after_tool(context, provider: str, call_id: str, tool: str, result: str) -> None:
    messages = [
        {"role": "user", "content": "Status?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "name": tool, "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": call_id, "content": json.loads(result)},
    ]
    _request(context, provider, "m", messages)


@when(
    'a text completion is requested from "{provider}" with the model "{model}" and the message "{text}"'
)
def step_text_completion(context, provider: str, model: str, text: str) -> None:
    context.completion_text = context.run(get_completion, provider, model, "You are helpful.", text)


@then('the chat result content is "{content}"')
def step_content(context, content: str) -> None:
    assert context.chat_result.content == content


@then('the chat result stop reason is "{reason}"')
def step_stop_reason(context, reason: str) -> None:
    assert context.chat_result.stop_reason == reason, context.chat_result


@then("the chat result has {count:d} tool calls")
def step_tool_call_count(context, count: int) -> None:
    assert len(context.chat_result.tool_calls) == count


@then("the tool call {number:d} is \"{name}\" with the arguments '{arguments}'")
def step_tool_call(context, number: int, name: str, arguments: str) -> None:
    call = context.chat_result.tool_calls[number - 1]
    assert call.name == name and call.arguments == json.loads(arguments), call


@then('the provider received the system prompt "{prompt}"')
def step_system_prompt(context, prompt: str) -> None:
    request = context.provider.request
    system = request.get("system") or request["messages"][0]["content"]
    assert system == prompt, request


@then("the provider received {count:d} messages")
def step_message_count(context, count: int) -> None:
    messages = [m for m in context.provider.request["messages"] if m["role"] != "system"]
    assert len(messages) == count


@then('the provider received the tool definitions "{names}" in the function calling format')
def step_openai_tools(context, names: str) -> None:
    tools = context.provider.request["tools"]
    assert [t["function"]["name"] for t in tools] == [n.strip() for n in names.split(",")]
    assert all(t["type"] == "function" for t in tools)


@then('the provider received the tool definitions "{names}" in the Anthropic format')
def step_anthropic_tools(context, names: str) -> None:
    tools = context.provider.request["tools"]
    assert [t["name"] for t in tools] == [n.strip() for n in names.split(",")]
    assert all(t["input_schema"]["type"] == "object" for t in tools)


@then(
    "the provider received the assistant tool call \"{call_id}\" and the tool message with the content '{content}'"
)
def step_openai_tool_messages(context, call_id: str, content: str) -> None:
    messages = context.provider.request["messages"]
    assistant = next(m for m in messages if m["role"] == "assistant")
    tool = next(m for m in messages if m["role"] == "tool")
    assert assistant["tool_calls"][0]["id"] == call_id
    assert assistant["tool_calls"][0]["type"] == "function"
    assert tool["tool_call_id"] == call_id and json.loads(tool["content"]) == json.loads(content)


@then(
    "the provider received the tool use \"{call_id}\" and the tool result with the content '{content}'"
)
def step_anthropic_tool_messages(context, call_id: str, content: str) -> None:
    messages = context.provider.request["messages"]
    assistant = next(m for m in messages if m["role"] == "assistant")
    result = messages[-1]["content"][0]
    assert assistant["content"][0] == {
        "type": "tool_use",
        "id": call_id,
        "name": "team_status",
        "input": {},
    }
    assert result["type"] == "tool_result" and result["tool_use_id"] == call_id
    assert json.loads(result["content"]) == json.loads(content)


@then('the request fails with "{error}"')
def step_fails(context, error: str) -> None:
    assert context.error == error, context.error


@then('the text completion is "{text}"')
def step_text(context, text: str) -> None:
    assert context.completion_text == text
