# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the tool features: run tools with a database session and read their results."""

import json
import re

import httpx
from behave import given, step, then, when
from sqlalchemy import select
from team.models import Task
from team.services import ToolService


def _expand(context, text: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: str(context.vars[m.group(1)]), text)


def _field(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


@step("the agent runs the tool \"{name}\" with '{params}'")
def step_run_tool(context, name: str, params: str) -> None:
    context.tool_result = context.run_tool(name, json.loads(_expand(context, params)))


@step('I remember the tool result field "{field}" as "{name}"')
def step_remember(context, field: str, name: str) -> None:
    context.vars[name] = _field(context.tool_result, field)


@then('the tool result field "{field}" is "{value}"')
def step_result_field(context, field: str, value: str) -> None:
    assert str(_field(context.tool_result, field)) == _expand(context, value), context.tool_result


@then("the tool result has no results")
def step_no_results(context) -> None:
    assert context.tool_result["results"] == [], context.tool_result


@then('the catalog contains the tools "{names}"')
def step_catalog_names(context, names: str) -> None:
    catalog = {tool["name"] for tool in context.response.json()}
    wanted = {name.strip() for name in names.split(",")}
    assert wanted <= catalog, wanted - catalog


@then("every tool of the catalog has a description and parameters")
def step_catalog_shape(context) -> None:
    for tool in context.response.json():
        assert tool["description"] and tool["parameters"]["type"] == "object", tool


@when('the definitions of the tools "{names}" are requested')
def step_definitions(context, names: str) -> None:
    context.definitions = ToolService().get_tool_definitions([n.strip() for n in names.split(",")])


@then("{count:d} tool definitions are returned")
def step_definition_count(context, count: int) -> None:
    assert len(context.definitions) == count, context.definitions


@then('the definition of "{name}" has the type "{kind}"')
def step_definition_type(context, name: str, kind: str) -> None:
    definition = context.definitions[0]
    assert definition["type"] == kind and definition["function"]["name"] == name


@then('the team has a pending task "{title}" created by the agent "{agent}"')
def step_pending_task(context, title: str, agent: str) -> None:
    async def load() -> tuple[str, str, dict]:
        async with context.session_factory() as session:
            result = await session.execute(select(Task).where(Task.title == title))
            task = result.scalar_one()
            return task.status, task.team_id, task.input_data

    status, team_id, input_data = context.run(load)
    assert status == "pending" and str(team_id) == context.vars["team_id"]
    assert input_data["created_by_agent_name"] == agent
    assert input_data["created_by_agent_id"] == context.vars["agent_id"]


@given('an external API answering "{body}" with the status {status:d}')
def step_external_api(context, body: str, status: int) -> None:
    context.external_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        context.external_requests.append((request.method, request.url.path))
        return httpx.Response(status, text=body)

    service = ToolService()
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    context.tool_service = service


@then('the external API received a {method} request on "{path}"')
def step_external_received(context, method: str, path: str) -> None:
    assert (method, path) in context.external_requests, context.external_requests
