# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the service tools: an in-memory HTTP transport plays the other services."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from behave import given, step, then, when
from team.services import ToolService
from team.services.tools._http import get_service_client


@given("the services answer '{body}' with the status {status:d}")
def step_services_answer(context, body: str, status: int) -> None:
    context.service_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        context.service_requests.append(request)
        try:
            return httpx.Response(status, json=json.loads(body))
        except ValueError:
            return httpx.Response(status, text=body)

    service = ToolService()
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    context.tool_service = service


@given('the global billing base URL is "{url}"')
def step_global_billing(context, url: str) -> None:
    settings = SimpleNamespace(billing_base_url=url, oauth2_client_secret="global-secret")
    patcher = patch("team.services.tools.billing_ops.get_settings", return_value=settings)
    patcher.start()
    context.add_cleanup(patcher.stop)


@step("the agent runs the tool \"{name}\" with '{params}' and the credentials '{credentials}'")
def step_run_with_credentials(context, name: str, params: str, credentials: str) -> None:
    context.tool_result = context.run_tool(
        name, json.loads(params), agent_config={"credentials": json.loads(credentials)}
    )


def _last(context) -> httpx.Request:
    assert context.service_requests, "the service received no request"
    return context.service_requests[-1]


@then('the services received a {method} request on "{path}"')
def step_received(context, method: str, path: str) -> None:
    request = _last(context)
    assert (request.method, request.url.path) == (method, path), (
        request.method,
        request.url.path,
    )


@then('the services received the query "{query}"')
def step_received_query(context, query: str) -> None:
    assert _last(context).url.query.decode() == query, _last(context).url.query


@then('the services received the bearer token "{token}"')
def step_received_token(context, token: str) -> None:
    assert _last(context).headers["authorization"] == f"Bearer {token}"


@then("the services received the JSON body '{body}'")
def step_received_body(context, body: str) -> None:
    assert json.loads(_last(context).content) == json.loads(body), _last(context).content


@when('the service client is requested for "{url}"')
def step_client_for(context, url: str) -> None:
    async def request():
        service = ToolService()
        client, effective, should_close = await get_service_client(service, url)
        if should_close:
            await client.aclose()
        return effective, should_close

    context.client_choice = context.run(request)


@then('the effective base URL is "{url}" and the client must be closed')
def step_must_close(context, url: str) -> None:
    assert context.client_choice == (url, True), context.client_choice


@then('the effective base URL is "{url}" and the client is shared')
def step_shared(context, url: str) -> None:
    assert context.client_choice == (url, False), context.client_choice
