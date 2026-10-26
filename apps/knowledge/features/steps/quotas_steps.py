# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the usage quotas and API call tracking feature."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from behave import given, then, when
from fastapi import FastAPI, HTTPException, Request

from knowledge.config import Settings
from knowledge.middleware.api_tracking import APITrackingMiddleware
from knowledge.models.enums import OwnerType, PlanType
from knowledge.services import plan_limits
from knowledge.services.quotas import QuotaExceededError, QuotaService, QuotaStatus


@given("the plan limits are configured as follows")
def step_configure_limits(context):
    configured: dict[str, dict[str, int]] = {}
    for row in context.table:
        configured.setdefault(row["plan"], {})[row["limit"].strip()] = int(row["value"])
    settings = Settings(_env_file=None, quota_fallback_limits=configured)
    patcher = patch.object(plan_limits, "get_settings", return_value=settings)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the "{plan}" plan')
def step_plan(context, plan):
    context.plan = PlanType(plan)


@then('the plan limit "{limit}" should be {value:d}')
def step_plan_limit(context, limit, value):
    assert asyncio.run(QuotaService(None).get_limit(context.plan, limit)) == value


@given("a quota with limit {limit:d} and {used:d} used")
def step_quota(context, limit, used):
    context.quota = QuotaStatus(quota_type="max_collections", current=used, limit=limit)


@given("an unlimited quota with {used:d} used")
def step_unlimited_quota(context, used):
    context.quota = QuotaStatus(
        quota_type="max_collections", current=used, limit=-1, is_unlimited=True
    )


@then("the quota should not be exceeded")
def step_not_exceeded(context):
    assert not context.quota.is_exceeded


@then("the quota should be exceeded")
def step_exceeded(context):
    assert context.quota.is_exceeded


@then("the quota should have {remaining:d} remaining")
def step_remaining(context, remaining):
    assert context.quota.remaining == remaining


@then("the quota should be {percent:d} percent used")
def step_percent(context, percent):
    assert round(context.quota.percentage_used) == percent


@then("the quota should be near its limit")
def step_near_limit(context):
    assert context.quota.is_near_limit


class _CountingQuotaService(QuotaService):
    """Real quota logic with the database lookups replaced by fixed values."""

    def __init__(self, plan: PlanType, collections: int):
        super().__init__(None)
        self._plan = plan
        self._collections = collections

    async def get_owner_plan(self, owner_type, owner_id):
        return self._plan

    async def get_collection_count_for_owner(self, owner_type, owner_id):
        return self._collections


@given('a user on the "{plan}" plan owning {count:d} collections')
def step_user_collections(context, plan, count):
    context.owner_type = OwnerType.USER
    context.quota_service = _CountingQuotaService(PlanType(plan), count)


@given('an organization on the "{plan}" plan owning {count:d} collections')
def step_org_collections(context, plan, count):
    context.owner_type = OwnerType.ORGANIZATION
    context.quota_service = _CountingQuotaService(PlanType(plan), count)


@when("the {_who} tries to create a collection")
def step_try_create(context, _who):
    context.refusal = None
    try:
        asyncio.run(
            context.quota_service.enforce_collection_quota_for_owner(context.owner_type, uuid4())
        )
    except QuotaExceededError as error:
        context.refusal = error


@then('the creation should be refused with the quota "{quota}" at {current:d} of {limit:d}')
def step_refused(context, quota, current, limit):
    error = context.refusal
    assert error is not None, "creation was accepted"
    assert (error.quota_type, error.current, error.limit) == (quota, current, limit)


@then("the creation should be accepted")
def step_accepted(context):
    assert context.refusal is None, context.refusal


class _RecordingQuotaService:
    def __init__(self, recorder):
        self.recorder = recorder

    async def record_api_call(self, tenant_id):
        if self.recorder.unavailable:
            raise RuntimeError("usage store unavailable")
        self.recorder.calls.append(tenant_id)


class _Recorder:
    def __init__(self):
        self.calls = []
        self.unavailable = False


class _FakeSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        session = AsyncMock()
        return session

    async def __aexit__(self, *exc):
        return False


@given("an API with call tracking")
def step_tracked_api(context):
    probe = FastAPI()
    probe.add_middleware(APITrackingMiddleware)

    @probe.get("/api/v1/ping")
    async def ping(request: Request):
        request.state.tenant_id = UUID(request.headers["X-Tenant-ID"])
        return {"ok": True}

    @probe.get("/api/v1/missing")
    async def missing(request: Request):
        request.state.tenant_id = UUID(request.headers["X-Tenant-ID"])
        raise HTTPException(status_code=404)

    @probe.get("/health")
    async def health(request: Request):
        request.state.tenant_id = UUID(request.headers["X-Tenant-ID"])
        return {"status": "healthy"}

    context.recorder = _Recorder()
    context.tracked_api = probe
    for target, fake in (
        ("knowledge.middleware.api_tracking.async_session_factory", _FakeSessionFactory()),
        (
            "knowledge.middleware.api_tracking.QuotaService",
            lambda db: _RecordingQuotaService(context.recorder),
        ),
    ):
        patcher = patch(target, fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


@given("the usage store is unavailable")
def step_store_unavailable(context):
    context.recorder.unavailable = True


@when('a client calls "{path}" for tenant "{tenant}"')
def step_call_tracked(context, path, tenant):
    context.response = context.call_app(
        context.tracked_api, "GET", path, headers={"X-Tenant-ID": tenant}
    )


@then('{count:d} API call should be recorded for tenant "{tenant}"')
def step_calls_recorded(context, count, tenant):
    assert context.recorder.calls == [UUID(tenant)] * count, context.recorder.calls


@then("no API call should be recorded")
def step_no_calls(context):
    assert context.recorder.calls == []
