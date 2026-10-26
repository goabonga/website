# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the multi-tenant resolution feature.

The tenant lookups normally query PostgreSQL; here the session factory used by
the middleware is replaced by a fake that answers from a small in-memory list
by reading the bound parameters of the statement.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from behave import given, then, when
from fastapi import FastAPI
from pydantic import ValidationError

from knowledge.middleware.tenant import TenantMiddleware, get_tenant_context
from knowledge.schemas.tenant import TenantCreate
from knowledge.services.tenants import TenantService


class _Directory:
    """In-memory tenant directory."""

    def __init__(self):
        self.by_slug = {}
        self.by_domain = {}


class _FakeSessionFactory:
    def __init__(self, directory):
        self.directory = directory

    def __call__(self):
        return self

    async def __aenter__(self):
        session = MagicMock()

        async def execute(statement):
            params = statement.compile().params
            row = None
            if "slug_1" in params:
                row = self.directory.by_slug.get(params["slug_1"])
            elif "custom_domain_1" in params:
                row = self.directory.by_domain.get(params["custom_domain_1"])
            result = MagicMock()
            result.first.return_value = row
            return result

        session.execute = execute
        return session

    async def __aexit__(self, *exc):
        return False


@given('the base domain "{domain}"')
def step_base_domain(context, domain):
    context.base_domain = domain
    context.directory = _Directory()
    patcher = patch(
        "knowledge.database.async_session_factory", _FakeSessionFactory(context.directory)
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('an active tenant "{slug}" with id "{tenant_id}"')
def step_tenant(context, slug, tenant_id):
    context.directory.by_slug[slug] = SimpleNamespace(id=UUID(tenant_id), slug=slug)


@given('the tenant "{slug}" has the active custom domain "{domain}"')
def step_custom_domain(context, slug, domain):
    context.directory.by_domain[domain] = context.directory.by_slug[slug]


@given("an API behind the tenant middleware")
def step_tenant_api(context):
    probe = FastAPI()
    probe.add_middleware(
        TenantMiddleware, base_domain=context.base_domain, custom_domain_lookup=True
    )

    @probe.get("/api/v1/ping")
    async def ping():
        tenant = get_tenant_context()
        if tenant is None:
            return {"tenant": None}
        return {
            "tenant": {
                "id": tenant.tenant_id,
                "slug": tenant.tenant_slug,
                "method": tenant.resolution_method,
            }
        }

    context.tenant_api = probe


@when('a client requests "{path}" on host "{host}"')
def step_request_on_host(context, path, host):
    context.response = context.call_app(
        context.tenant_api, "GET", path, headers={"Host": host}, follow_redirects=False
    )


def _tenant(context):
    return context.response.json()["tenant"]


@then('the resolved tenant slug should be "{slug}"')
def step_slug(context, slug):
    assert _tenant(context)["slug"] == slug


@then('the tenant should be resolved by "{method}"')
def step_method(context, method):
    assert _tenant(context)["method"] == method


@then('the resolved tenant id should be "{tenant_id}"')
def step_tenant_id(context, tenant_id):
    assert _tenant(context)["id"] == tenant_id


@then("no tenant should be resolved")
def step_no_tenant(context):
    assert _tenant(context) is None


@then('the redirect location should be "{location}"')
def step_location(context, location):
    assert context.response.headers["location"] == location


@when('I create the tenant "{name}" with slug "{slug}"')
def step_create_tenant(context, name, slug):
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    context.new_tenant = asyncio.run(TenantService(db).create(TenantCreate(name=name, slug=slug)))


@then('the new tenant should be on the "{plan}" plan')
def step_new_tenant_plan(context, plan):
    assert context.new_tenant.plan.value == plan


@when('I try to create the tenant "{name}" with slug "{slug}"')
def step_try_create_tenant(context, name, slug):
    try:
        TenantCreate(name=name, slug=slug)
        context.rejected = False
    except ValidationError:
        context.rejected = True


@then("the tenant creation should be rejected")
def step_rejected(context):
    assert context.rejected
