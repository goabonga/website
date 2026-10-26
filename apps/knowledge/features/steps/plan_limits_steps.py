# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the plan limits feature.

The quota service and the billing client are real. The billing service is an httpx mock
transport, Redis is a dictionary and the OAuth2 token is faked.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from behave import given, then, when

from knowledge.config import Settings
from knowledge.models.enums import PlanType
from knowledge.services import plan_limits
from knowledge.services.billing import BillingClient
from knowledge.services.quotas import QuotaService


class _FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


def _table(context):
    return {row["limit"]: int(row["value"]) for row in context.table}


def _billing(context, handler, configured=True):
    settings = Settings(
        _env_file=None,
        billing_api_url="http://billing.test" if configured else "",
        billing_app_slug="my-app",
        billing_saas_id="saas-1",
    )
    with patch("knowledge.services.billing.get_settings", return_value=settings):
        client = BillingClient()
    client._get_access_token = AsyncMock(return_value="tok")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    redis = _FakeRedis()

    async def get_http_client():
        return http

    async def get_redis_client():
        return redis

    client.get_http_client = get_http_client
    client.get_redis_client = get_redis_client
    context.billing_client = client
    _patch(context, (plan_limits, "get_billing_client"), lambda: client, attribute=True)


@given("the fail-safe limits are configured as follows")
def step_failsafe(context):
    configured: dict[str, dict[str, int]] = {}
    for row in context.table:
        configured.setdefault(row["plan"], {})[row["limit"]] = int(row["value"])
    context.settings = Settings(
        _env_file=None, quota_fallback_limits=configured, billing_failure_backoff=30
    )
    _patch(context, (plan_limits, "get_settings"), lambda: context.settings, attribute=True)
    plan_limits.reset_billing_backoff()
    context.add_cleanup(plan_limits.reset_billing_backoff)
    context.billing_calls = 0


@given('the billing service defines the plan "{slug}" with the limits')
def step_billing_plan(context, slug):
    payload = {
        "plans": [{"id": slug, "slug": slug, "name": slug.title(), "limits": _table(context)}]
    }

    def handler(request):
        context.billing_calls += 1
        return httpx.Response(200, json=payload)

    context.billing_handler = handler
    _billing(context, handler)


@given("the billing service cannot be reached")
def step_failing(context):
    def handler(request):
        context.billing_calls += 1
        return httpx.Response(503, text="unavailable")

    _billing(context, handler)


@given("the billing service is not configured")
def step_not_configured(context):
    _billing(context, lambda request: httpx.Response(500), configured=False)


@when('the application asks for the limit "{limit}" of the "{plan}" plan')
def step_ask(context, limit, plan):
    service = QuotaService(None)
    context.limit = asyncio.run(service.get_limit(PlanType(plan), limit))


@when("billing recovers and the back-off is over")
def step_recovers(context):
    context.billing_client.cache_ttl = 0

    def handler(request):
        context.billing_calls += 1
        return httpx.Response(
            200,
            json={
                "plans": [
                    {"id": "pro", "slug": "pro", "name": "Pro", "limits": {"max_collections": 50}}
                ]
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def get_http_client():
        return http

    context.billing_client.get_http_client = get_http_client
    plan_limits.reset_billing_backoff()


@then("the limit should be {value:d}")
def step_limit(context, value):
    assert context.limit == value, context.limit


@then("billing should have been asked once")
def step_asked_once(context):
    assert context.billing_calls == 1, context.billing_calls
