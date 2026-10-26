# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the Python client SDK feature."""

import httpx
from behave import given, then, when
from custom_domain import client as sdk
from custom_domain.models import CustomDomain
from fakes import AsgiBridgeTransport
from sqlalchemy import select

BASE_URL = "http://test"


def find_domain(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


@given("the SDK is connected to the service")
def step_sdk_connected(context):
    context.sdk = sdk.CustomDomainClient(BASE_URL, access_token=context.token)
    context.sdk._http = httpx.Client(transport=AsgiBridgeTransport(context.app, context.loop))


@given('the domain "{name}" has the error "{message}"')
def step_domain_error(context, name, message):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        domain.error_message = message
        session.commit()


def attempt(context, call):
    context.sdk_error = None
    context.sdk_result = None
    try:
        context.sdk_result = call()
    except sdk.CustomDomainError as error:
        context.sdk_error = error


@when('I register the domain "{name}" for the owner "{owner}" with the SDK')
def step_register(context, name, owner):
    attempt(
        context,
        lambda: context.sdk.domains.create(domain=name, owner_id=owner, owner_type="organization"),
    )


@then('the SDK returns a pending domain with the CNAME target "{target}"')
def step_pending(context, target):
    assert context.sdk_error is None, context.sdk_error
    assert context.sdk_result.status == sdk.DomainStatus.PENDING
    assert context.sdk_result.cname_target == target


@then("the SDK can read the domain back")
def step_read_back(context):
    domain = context.sdk.domains.get(context.sdk_result.id)
    assert domain.domain == "shop.example.com"
    assert domain.status == sdk.DomainStatus.PENDING


@when('I list the domains with the SDK filtered on the status "{status}"')
def step_list_filtered(context, status):
    attempt(context, lambda: context.sdk.domains.list(status=sdk.DomainStatus(status)))


@when("I list the domains with the SDK")
def step_list(context):
    attempt(context, lambda: context.sdk.domains.list())


@then("the SDK lists {count:d} domains")
def step_lists(context, count):
    assert context.sdk_error is None, context.sdk_error
    assert len(context.sdk_result.items) == count


@when('I look up "{name}" with the SDK')
def step_lookup(context, name):
    attempt(context, lambda: context.sdk.domains.lookup(name))


@then('the SDK returns the owner "{owner}"')
def step_owner(context, owner):
    assert context.sdk_result.owner_id == owner


@when("I read an unknown domain with the SDK")
def step_unknown(context):
    attempt(context, lambda: context.sdk.domains.get("00000000-0000-0000-0000-000000000000"))


@then('the SDK raises "{name}" with the status {status:d}')
def step_raises(context, name, status):
    assert type(context.sdk_error).__name__ == name, context.sdk_error
    assert context.sdk_error.status_code == status


@then('the SDK raises "{name}" mentioning "{text}"')
def step_raises_mentioning(context, name, text):
    assert type(context.sdk_error).__name__ == name, context.sdk_error
    assert text in str(context.sdk_error), context.sdk_error


@when('I wait for the domain "{name}" to become active with the SDK')
def step_wait(context, name):
    domain_id = str(find_domain(context, name).id)
    attempt(
        context, lambda: context.sdk.domains.wait_for_active(domain_id, timeout=5, poll_interval=0)
    )


@then('the SDK returns the active domain "{name}"')
def step_active(context, name):
    assert context.sdk_error is None, context.sdk_error
    assert context.sdk_result.domain == name
    assert context.sdk_result.status == sdk.DomainStatus.ACTIVE


@given("the service rejects the first token and accepts a refreshed one")
def step_refresh(context):
    context.refreshes = 0
    seen = []

    def handler(request):
        seen.append(request.headers["authorization"])
        if len(seen) == 1:
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"items": [], "total": 0, "limit": 20, "offset": 0})

    def refresher():
        context.refreshes += 1
        return "fresh-token"

    context.sdk = sdk.CustomDomainClient(BASE_URL, "stale-token", token_refresher=refresher)
    context.sdk._http = httpx.Client(transport=httpx.MockTransport(handler))


@then("the token was refreshed {count:d} times")
def step_refreshed(context, count):
    assert context.sdk_error is None, context.sdk_error
    assert context.refreshes == count


@when("I read the clients and the overview with the SDK")
def step_admin(context):
    context.sdk_clients = context.sdk.clients.list()
    context.sdk_overview = context.sdk.stats.overview()


@then("the SDK reports {clients:d} clients and {domains:d} domains")
def step_admin_counts(context, clients, domains):
    assert context.sdk_clients.total == clients
    assert context.sdk_overview.domains.total == domains


@when("I list the domains with the async SDK")
def step_async_list(context):
    async def run():
        async with sdk.AsyncCustomDomainClient(BASE_URL, access_token=context.token) as client:
            await client._http.aclose()
            client._http = httpx.AsyncClient(transport=httpx.ASGITransport(app=context.app))
            return await client.list_domains()

    context.sdk_error = None
    context.sdk_result = context.loop.run_until_complete(run())


@when('I delete the domain "{name}" with the SDK')
def step_delete(context, name):
    domain_id = str(find_domain(context, name).id)
    attempt(context, lambda: context.sdk.domains.delete(domain_id))


@when('I read the domain "{name}" with the SDK')
def step_read_domain(context, name):
    domain_id = str(find_domain(context, name).id)
    attempt(context, lambda: context.sdk.domains.get(domain_id))


@then('the SDK reports the status "{status}"')
def step_reports_status(context, status):
    assert context.sdk_error is None, context.sdk_error
    result = context.sdk_result
    assert (result["status"] if isinstance(result, dict) else result.status) == status


def run_async_sdk(context, call):
    async def run():
        async with sdk.AsyncCustomDomainClient(BASE_URL, access_token=context.token) as client:
            await client._http.aclose()
            client._http = httpx.AsyncClient(transport=httpx.ASGITransport(app=context.app))
            return await call(client)

    context.sdk_error = None
    context.sdk_result = None
    try:
        context.sdk_result = context.loop.run_until_complete(run())
    except sdk.CustomDomainError as error:
        context.sdk_error = error


@when('the async SDK verifies the domain "{name}"')
def step_async_verify(context, name):
    domain_id = str(find_domain(context, name).id)
    run_async_sdk(context, lambda client: client.verify_domain(domain_id))


@when('the async SDK provisions the domain "{name}"')
def step_async_provision(context, name):
    domain_id = str(find_domain(context, name).id)
    run_async_sdk(context, lambda client: client.provision_domain(domain_id))


@when("the async SDK reads an unknown domain")
def step_async_unknown(context):
    run_async_sdk(context, lambda client: client.get_domain("00000000-0000-0000-0000-000000000000"))
