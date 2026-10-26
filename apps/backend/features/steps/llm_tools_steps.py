# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the LLM client and tool registry feature."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.llm.client import OpenAIClient, _generation_params
from backend.llm.tools import ToolContext, ToolRegistry, ToolResult, tool_registry
from behave import given, then, when


def _names(text):
    return [name.strip() for name in text.split(",") if name.strip()]


@given(
    'a tool registry with a public tool "{public}" and a tool "{private}" '
    'requiring the scope "{scope}"'
)
def step_registry(context, public, private, scope):
    registry = ToolRegistry()
    schema = {"type": "object", "properties": {"text": {"type": "string"}}}

    @registry.register(name=public, description="Echo the text", parameters=schema)
    async def echo(text: str) -> ToolResult:
        return ToolResult(success=True, data=text)

    @registry.register(
        name=private, description="Report", parameters=schema, required_scopes={scope}
    )
    async def report(text: str) -> ToolResult:
        return ToolResult(success=True, data=text)

    context.registry = registry


def _list(context, scopes):
    listed = context.registry.get_openai_tools(scopes)
    context.listed = [tool["function"]["name"] for tool in listed]


@when("the tools are listed for an anonymous user")
def step_list_anonymous(context):
    _list(context, None)


@when('the tools are listed for the scopes "{scopes}"')
def step_list_scopes(context, scopes):
    _list(context, set(_names(scopes)))


@then('the listed tools should be "{names}"')
def step_listed(context, names):
    assert context.listed == _names(names), context.listed


@when('the tool "{name}" is executed with the text "{text}"')
def step_execute(context, name, text):
    context.result = asyncio.run(context.registry.execute(name, {"text": text}))


@when('the tool "{name}" is called by a caller with the scopes "{scopes}" and the text "{text}"')
def step_execute_scopes(context, name, scopes, text):
    tool_context = ToolContext(scopes=set(_names(scopes)))
    context.result = asyncio.run(context.registry.execute(name, {"text": text}, tool_context))


@then('the tool should succeed with the data "{data}"')
def step_success(context, data):
    assert context.result.success is True and context.result.data == data, context.result


@then('the tool should fail with the error "{error}"')
def step_failure(context, error):
    assert context.result.success is False and context.result.error == error, context.result


@then('the global registry should contain the tools "{names}"')
def step_global(context, names):
    for name in _names(names):
        assert tool_registry.get_tool(name) is not None, name


@then('the generation parameters for "{model}" should include a temperature')
def step_with_temperature(context, model):
    params = _generation_params(model, 0.7, 100)
    assert params == {"max_completion_tokens": 100, "temperature": 0.7}


@then('the generation parameters for "{model}" should not include a temperature')
def step_without_temperature(context, model):
    assert _generation_params(model, 0.7, 100) == {"max_completion_tokens": 100}


@given(
    'the model answers "{content}" using {prompt:d} prompt tokens and {completion:d} completion tokens'
)
def step_model_answer(context, content, prompt, completion):
    message = SimpleNamespace(content=content, role="assistant", tool_calls=None)
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
    patcher = patch("backend.llm.client.AsyncOpenAI")
    client_cls = patcher.start()
    context.patches["openai"] = patcher
    client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)


@when('the client sends the message "{text}"')
def step_send(context, text):
    client = OpenAIClient()
    context.reply = asyncio.run(client.chat([{"role": "user", "content": text}]))


@then('the reply content should be "{content}"')
def step_reply(context, content):
    assert context.reply["content"] == content
    assert context.reply["tool_calls"] is None


@then("the reported usage should be {prompt:d} prompt tokens and {completion:d} completion tokens")
def step_usage(context, prompt, completion):
    assert context.reply["usage"] == {"prompt_tokens": prompt, "completion_tokens": completion}
