# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the landing, dashboard, pricing and download pages.

Templates and routes are real. The database is an in-memory store, the billing
service and the quota service are fakes, and the signed-in user is injected
through the web authentication dependency.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from behave import given, then, when
from fakes import FakeSession, Store

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.models import Collection, Organization, OrganizationMember
from knowledge.models.enums import OrganizationMemberRole, PlanType
from knowledge.services.billing import BillingAPIError, Plan, PlanPrice
from knowledge.services.quotas import QuotaStatus, UsageStats


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


class _SequenceSession(FakeSession):
    """Answers the dashboard queries in order: workspaces, counts, recent collections."""

    def __init__(self, store, results):
        super().__init__(store)
        self.results = list(results)
        self.fallback = FakeSession.execute

    async def execute(self, statement):
        if hasattr(statement, "column_descriptions"):
            entity = statement.column_descriptions[0].get("entity")
            if entity is not None and entity.__name__.startswith("Mcp"):
                return await self.fallback(self, statement)
        if not self.results:
            return await self.fallback(self, statement)
        return self.results.pop(0)


def _scalars(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@given("the web pages database is in memory")
def step_database(context):
    context.store = Store()
    context.session = FakeSession(context.store)
    context.web_cookies = {}

    async def fake_db():
        yield context.session

    context.internal_app.dependency_overrides[get_db] = fake_db


@when('I open "{path}" carrying an access token')
def step_open_with_token(context, path):
    context.response = context.call(
        "GET", path, headers={"Cookie": "access_token=any"}, follow_redirects=False
    )


# --- pricing ----------------------------------------------------------------


class _FakeBilling:
    def __init__(self, plans=None, error=None):
        self.plans = plans or []
        self.error = error
        self.is_configured = True

    async def get_plans(self):
        if self.error:
            raise self.error
        return self.plans


def _plan(name, order, cents):
    return Plan(
        id=name.lower(),
        slug=name.lower(),
        name=name,
        description=f"{name} plan",
        features=[],
        limits=None,
        prices=[PlanPrice(id=f"{name}-m", currency="usd", unit_amount=cents, interval="month")],
        is_recommended=name == "Pro",
        sort_order=order,
    )


@given(
    'the billing service offers the plans "{first}" at {first_cents:d} cents and "{second}" at {second_cents:d} cents per month'
)
def step_billing_plans(context, first, first_cents, second, second_cents):
    billing = _FakeBilling([_plan(first, 1, first_cents), _plan(second, 2, second_cents)])
    _patch(context, "knowledge.routes.web.home.get_billing_client", lambda: billing)


@given("the billing service is failing")
def step_billing_failing(context):
    billing = _FakeBilling(error=BillingAPIError("billing is down"))
    _patch(context, "knowledge.routes.web.home.get_billing_client", lambda: billing)


# --- dashboard --------------------------------------------------------------


def _sign_in(context, name, tenant):
    user = User(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), name=name, email="alice@example.test"
    )
    member = (
        OrganizationMember(
            organization_id=tenant.id, user_id=user.id, role=OrganizationMemberRole.OWNER
        )
        if tenant
        else None
    )
    context.internal_app.dependency_overrides[get_web_auth_context] = lambda: WebAuthContext(
        user=user, tenant=tenant, tenant_member=member
    )


@given('I am signed in as "{name}" in the workspace "{workspace}" on the "{plan}" plan')
def step_signed_in(context, name, workspace, plan):
    context.tenant = Organization(id=uuid4(), name=workspace, slug="acme", plan=PlanType(plan))
    _sign_in(context, name, context.tenant)


@given('I am signed in as "{name}" without a workspace')
def step_signed_in_without_workspace(context, name):
    context.tenant = None
    _sign_in(context, name, None)


@given("the workspace holds {collections:d} collections and {documents:d} documents")
def step_workspace_content(context, collections, documents):
    recent = [
        Collection(
            id=uuid4(),
            name=f"Collection {i}",
            slug=f"c{i}",
            document_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for i in range(collections)
    ]
    context.session = _SequenceSession(
        context.store,
        [_scalars([context.tenant]), _scalar(collections), _scalar(documents), _scalars(recent)],
    )
    context.dashboard_counts = (collections, documents)

    class FakeQuota:
        def __init__(self, db):
            pass

        async def get_usage(self, tenant_id):
            limits = {"max": 3}
            return UsageStats(
                collections=QuotaStatus("max_collections", collections, limits["max"]),
                documents_total=QuotaStatus("max_total_documents", documents, 200),
                api_calls_month=QuotaStatus("max_api_calls_per_month", 0, 1000),
                storage_bytes=QuotaStatus("max_storage_bytes", 2048, 50 * 1024 * 1024),
                plan=PlanType.FREE,
            )

    _patch(context, "knowledge.routes.web.home.QuotaService", FakeQuota)

    async def fake_db():
        yield context.session

    context.internal_app.dependency_overrides[get_db] = fake_db


@then("the dashboard should count {collections:d} collections and {documents:d} documents")
def step_dashboard_counts(context, collections, documents):
    page = context.response.text
    assert f'<div class="stat-value">{collections}</div>' in page
    assert f'<div class="stat-value">{documents}</div>' in page
