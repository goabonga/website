# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the billing integration feature.

The subscription webhook runs for real over a fake database session holding one
organization. The billing client talks to a mocked HTTP transport and a
dictionary standing in for Redis.
"""

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
from behave import given, then, when

from knowledge.config import get_settings
from knowledge.models import Organization, PlanType
from knowledge.services import event_dedupe
from knowledge.services.billing import BillingAPIError, BillingClient, checkout_redirect_urls

SECRET_HEADER = "X-Billing-Signature"


class _Session:
    def __init__(self, organization):
        self.organization = organization
        result = MagicMock()
        result.scalar_one_or_none.return_value = organization
        self.execute = AsyncMock(return_value=result)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('an organization "{org_id}" on the "{plan}" plan')
def step_organization(context, org_id, plan):
    context.org_id = org_id
    context.organization = Organization(
        id=UUID(org_id), name="Acme", slug="acme", plan=PlanType(plan)
    )
    _patch(
        context,
        "knowledge.routes.billing_webhooks.async_session_factory",
        _SessionFactory(_Session(context.organization)),
    )
    context.secret = ""


@given('the organization is on the "{plan}" plan')
@when('the organization is on the "{plan}" plan')
def step_organization_plan(context, plan):
    context.organization.plan = PlanType(plan)


@given('this application is the SaaS "{saas_id}" in billing')
def step_saas_id(context, saas_id):
    context.saas_id = saas_id
    settings = get_settings()
    _patch(context, (settings, "billing_saas_id"), saas_id, attribute=True)
    _patch(context, (settings, "billing_app_slug"), "my-app", attribute=True)
    _patch(context, (settings, "billing_event_ttl"), 600, attribute=True)
    # The processed event ids live in a dictionary instead of Redis
    context.processed_events = set()

    async def already_processed(namespace, event_id):
        return (namespace, event_id) in context.processed_events

    async def mark_processed(namespace, event_id, ttl_seconds):
        context.processed_events.add((namespace, event_id))

    _patch(context, (event_dedupe, "already_processed"), already_processed, attribute=True)
    _patch(context, (event_dedupe, "mark_processed"), mark_processed, attribute=True)


@given("this application has no SaaS id in billing")
def step_no_saas_id(context):
    _patch(context, (get_settings(), "billing_saas_id"), "", attribute=True)
    client = getattr(context, "billing_client", None)
    if client is not None:
        client._billing_saas_id = ""


@given('the webhook secret is "{secret}"')
def step_secret(context, secret):
    context.secret = secret
    _patch(context, (get_settings(), "billing_webhook_secret"), secret, attribute=True)


@given("no webhook secret is configured")
def step_no_secret(context):
    context.secret = ""
    _patch(context, (get_settings(), "billing_webhook_secret"), "", attribute=True)


def _event(context, event_type, plan, status, name=None, saas_id=None):
    context.event_counter = getattr(context, "event_counter", 0) + 1
    return json.dumps(
        {
            "id": f"evt-{context.event_counter}",
            "type": event_type,
            "created": "2026-01-01T00:00:00Z",
            "saas_id": saas_id or context.saas_id,
            "saas_slug": "my-app",
            "data": {
                "subscription_id": "sub_1",
                "customer_external_id": context.org_id,
                "status": status,
                "plan_name": name or plan.title(),
                "plan_slug": plan,
            },
        }
    ).encode()


def _post(context, payload, signature=None):
    context.last_event = (payload, signature)
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers[SECRET_HEADER] = signature
    context.response = context.call("POST", "/webhooks/billing", content=payload, headers=headers)


def _sign(secret, payload):
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@when(
    'the billing service sends a signed "{event_type}" event for plan "{plan}" with status "{status}"'
)
def step_signed_event(context, event_type, plan, status):
    payload = _event(context, event_type, plan, status)
    _post(context, payload, _sign(context.secret, payload))


@when(
    'the billing service sends a signed "{event_type}" event of the plan named "{name}" with slug "{plan}" and status "{status}"'
)
def step_signed_event_named(context, event_type, plan, name, status):
    payload = _event(context, event_type, plan, status, name=name)
    _post(context, payload, _sign(context.secret, payload))


@when(
    'the billing service sends a signed event of the SaaS "{saas_id}" for plan "{plan}" with status "{status}"'
)
def step_signed_event_other_saas(context, saas_id, plan, status):
    payload = _event(context, "subscription.updated", plan, status, saas_id=saas_id)
    _post(context, payload, _sign(context.secret, payload))


@when("the billing service sends the same event again")
def step_same_event_again(context):
    payload, signature = context.last_event
    _post(context, payload, signature)


@then("the response should say the event is a duplicate")
def step_duplicate(context):
    assert context.response.json() == {"status": "duplicate"}, context.response.json()


@when('the billing service sends an unsigned event for plan "{plan}" with status "{status}"')
def step_unsigned_event_with_plan(context, plan, status):
    _post(context, _event(context, "subscription.updated", plan, status))


@when("the billing service sends an event signed with the wrong secret")
def step_wrong_signature(context):
    payload = _event(context, "subscription.updated", "pro", "active")
    _post(context, payload, _sign("another-secret", payload))


@when("the billing service sends an unsigned event")
def step_unsigned_event(context):
    _post(context, _event(context, "subscription.updated", "pro", "active"))


@when("the billing service sends a signed payload that is not an event")
def step_garbage_payload(context):
    payload = b'{"hello": "world"}'
    _post(context, payload, _sign(context.secret, payload))


@then('the organization should be on the "{plan}" plan')
def step_organization_is_on(context, plan):
    assert context.organization.plan == PlanType(plan), context.organization.plan


# --- billing client -------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value


def _plan(name, order, monthly, yearly=None):
    prices = [{"id": f"{name}-m", "currency": "usd", "unit_amount": monthly, "interval": "month"}]
    if yearly is not None:
        prices.append(
            {"id": f"{name}-y", "currency": "usd", "unit_amount": yearly, "interval": "year"}
        )
    return {
        "id": name.lower(),
        "slug": name.lower(),
        "name": name,
        "sort_order": order,
        "is_recommended": name == "Pro",
        "features": [{"label": f"{name} feature"}],
        "limits": {"max_seats": 10} if name == "Pro" else None,
        "prices": prices,
    }


def _make_client(context, handler, configured=True):
    settings = get_settings()
    _patch(
        context,
        (settings, "billing_api_url"),
        "http://billing.test" if configured else "",
        attribute=True,
    )
    _patch(context, (settings, "billing_socket_path"), "", attribute=True)
    _patch(context, (settings, "billing_app_slug"), "my-app", attribute=True)
    _patch(context, (settings, "billing_saas_id"), "saas-of-knowledge", attribute=True)
    _patch(
        context,
        (settings, "billing_checkout_success_url"),
        "https://app.test/billing/ok",
        attribute=True,
    )
    _patch(
        context,
        (settings, "billing_checkout_cancel_url"),
        "https://app.test/billing/ko",
        attribute=True,
    )
    client = BillingClient()
    client._get_access_token = AsyncMock(return_value="tok")
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    redis = _FakeRedis()

    async def get_http_client():
        return http

    async def get_redis_client():
        return redis

    client.get_http_client = get_http_client
    client.get_redis_client = get_redis_client
    context.billing_client = client
    context.billing_calls = 0
    context.billing_requests = []
    context.plans = None
    context.billing_error = None


@given(
    'the billing API lists the plans "{first}" (order {first_order:d}) and "{second}" (order {second_order:d})'
)
def step_billing_plans(context, first, first_order, second, second_order):
    catalog = {
        "Pro": _plan("Pro", 0, 2900, 29000),
        "Free": _plan("Free", 0, 0),
    }
    payload = {
        "plans": [
            {**catalog[first], "sort_order": first_order},
            {**catalog[second], "sort_order": second_order},
        ]
    }

    def handler(request):
        context.billing_calls += 1
        context.billing_requests.append(request)
        return httpx.Response(200, json=payload)

    _make_client(context, handler)


@given("the billing API is failing")
def step_billing_failing(context):
    def handler(request):
        context.billing_calls += 1
        return httpx.Response(500, text="boom")

    _make_client(context, handler)


@given("the billing API is not configured")
def step_billing_unconfigured(context):
    _make_client(context, lambda request: httpx.Response(500), configured=False)


@when("the application loads the plans")
def step_load_plans(context):
    context.plans = asyncio.run(context.billing_client.get_plans())


@when("the application tries to load the plans")
def step_try_load_plans(context):
    try:
        asyncio.run(context.billing_client.get_plans())
    except BillingAPIError as error:
        context.billing_error = error


@then('the plans should be, in order, "{first}", "{second}"')
def step_plans_order(context, first, second):
    assert [plan.name for plan in context.plans] == [first, second]


def _find(context, name):
    return next(plan for plan in context.plans if plan.name == name)


@then('the plan "{name}" should cost "{monthly}" per month and "{yearly}" per year')
def step_plan_cost(context, name, monthly, yearly):
    plan = _find(context, name)
    assert plan.monthly_price.display_amount == monthly
    assert plan.yearly_price.display_amount == yearly


@then('the plan "{name}" should save {percent:d} percent when billed yearly')
def step_plan_savings(context, name, percent):
    assert _find(context, name).yearly_savings_percent == percent


@then('the plan "{name}" should be free')
def step_plan_free(context, name):
    assert _find(context, name).is_free


@then("the billing API should have been called {count:d} time")
def step_billing_calls(context, count):
    assert context.billing_calls == count, context.billing_calls


@then("loading the plans should fail with a billing error")
def step_billing_error(context):
    assert isinstance(context.billing_error, BillingAPIError)


@then("there should be no plans")
def step_no_plans(context):
    assert context.plans == []


@then('the billing API should have been asked for the plans of "{slug}" with a bearer token')
def step_plans_request(context, slug):
    request = context.billing_requests[0]
    assert request.url.path == f"/plans/{slug}", request.url
    assert request.headers["Authorization"] == "Bearer tok"


@then('the plan "{name}" should have the limit "{limit}" set to {value:d}')
def step_plan_limit(context, name, limit, value):
    assert _find(context, name).limits == {limit: value}


@given("the billing API accepts checkout sessions")
def step_billing_checkout(context):
    def handler(request):
        context.billing_requests.append(request)
        return httpx.Response(200, json={"session_id": "cs_1", "url": "https://pay.test/cs_1"})

    _make_client(context, handler)


@when('the application starts a checkout for the tenant "{tenant}"')
def step_start_checkout(context, tenant):
    success, cancel = checkout_redirect_urls()
    context.checkout = asyncio.run(
        context.billing_client.create_checkout_session(tenant, "price-1", success, cancel)
    )


@when('the application tries to start a checkout for the tenant "{tenant}"')
def step_try_checkout(context, tenant):
    context.billing_error = None
    try:
        success, cancel = checkout_redirect_urls()
        asyncio.run(
            context.billing_client.create_checkout_session(tenant, "price-1", success, cancel)
        )
    except BillingAPIError as error:
        context.billing_error = error


@then('the checkout request should carry the SaaS id "{saas_id}" and the configured URLs')
def step_checkout_request(context, saas_id):
    body = json.loads(context.billing_requests[-1].content)
    assert body["saas_id"] == saas_id
    assert body["success_url"] == "https://app.test/billing/ok"
    assert body["cancel_url"] == "https://app.test/billing/ko"
    assert context.checkout.url == "https://pay.test/cs_1"
