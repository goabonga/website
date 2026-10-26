# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace pages (switching, billing, settings).

Templates and routes are real. The database is the in-memory store, the signed-in
user is injected through the web authentication dependency and the billing
service is a configurable fake.
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from behave import given, then, when
from fakes import FakeBillingClient, FakeSession, Store

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.models import Organization, OrganizationMember
from knowledge.models.enums import OrganizationMemberRole, PlanType
from knowledge.services.billing import (
    BillingAPIError,
    Plan,
    PlanPrice,
    ProrationLineItem,
    TenantSubscription,
    UpgradePreview,
    UpgradeResult,
)
from knowledge.services.quotas import QuotaStatus, UsageStats

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


class _Quota:
    def __init__(self, db):
        pass

    async def get_usage(self, tenant_id):
        return UsageStats(
            collections=QuotaStatus("max_collections", 1, 3),
            documents_total=QuotaStatus("max_total_documents", 10, 200),
            api_calls_month=QuotaStatus("max_api_calls_per_month", 0, 1000),
            storage_bytes=QuotaStatus("max_storage_bytes", 2048, 50 * 1024 * 1024),
            plan=PlanType.FREE,
        )


@given("the workspace database is in memory")
def step_workspace_database(context):
    context.store = Store()
    context.session = FakeSession(context.store)

    async def fake_db():
        yield context.session

    context.internal_app.dependency_overrides[get_db] = fake_db
    _patch(context, "knowledge.routes.web.organizations.QuotaService", _Quota)


@given("the billing client is in memory")
def step_billing_client(context):
    context.billing = FakeBillingClient()
    _patch(
        context, "knowledge.routes.web.organizations.get_billing_client", lambda: context.billing
    )
    _patch(
        context,
        "knowledge.routes.web.organizations.checkout_redirect_urls",
        lambda: ("https://app.example.test/billing/ok", "https://app.example.test/billing/ko"),
    )


def _join(context, name, plan, role):
    organization = Organization(
        id=uuid4(), name=name, slug=name.lower(), plan=PlanType(plan), is_active=True
    )
    member = OrganizationMember(
        id=uuid4(),
        organization_id=organization.id,
        user_id=USER_ID,
        role=role,
        email="alice@example.test",
        created_at=datetime.now(UTC),
    )
    context.store.organizations[organization.id] = organization
    context.store.members[member.id] = member
    return organization, member


def _sign_in(context, organization, member):
    user = User(id=USER_ID, name="Alice", email="alice@example.test")
    context.tenant = organization
    context.member = member
    context.internal_app.dependency_overrides[get_web_auth_context] = lambda: WebAuthContext(
        user=user, tenant=organization, tenant_member=member
    )


@given('I am the owner of the workspace "{name}" on the "{plan}" plan')
def step_owner(context, name, plan):
    _sign_in(context, *_join(context, name, plan, OrganizationMemberRole.OWNER))


@given('I am an administrator of the workspace "{name}" on the "{plan}" plan')
def step_administrator(context, name, plan):
    _sign_in(context, *_join(context, name, plan, OrganizationMemberRole.ADMIN))


@given('I am a regular member of the workspace "{name}" on the "{plan}" plan')
def step_regular_member(context, name, plan):
    _sign_in(context, *_join(context, name, plan, OrganizationMemberRole.MEMBER))


@given("I am signed in without a workspace")
def step_without_workspace(context):
    user = User(id=USER_ID, name="Alice")
    context.internal_app.dependency_overrides[get_web_auth_context] = lambda: WebAuthContext(
        user=user, tenant=None, tenant_member=None
    )


@given('I also belong to the workspace "{name}"')
def step_also_belong(context, name):
    context.other, _ = _join(context, name, "free", OrganizationMemberRole.MEMBER)


@given('a workspace "{name}" exists that I do not belong to')
def step_foreign_workspace(context, name):
    context.other = Organization(id=uuid4(), name=name, slug=name.lower(), is_active=True)
    context.store.organizations[context.other.id] = context.other


# --- switching ----------------------------------------------------------------


@when('I switch to the workspace "{name}"')
def step_switch(context, name):
    context.response = context.call(
        "POST",
        "/organizations/switch",
        data={"organization_id": str(context.other.id)},
        follow_redirects=False,
    )


@then('the active workspace cookie should designate "{name}"')
def step_cookie_designates(context, name):
    cookies = context.response.headers.get_list("set-cookie")
    value = (
        next(c for c in cookies if c.startswith("active_tenant_id=")).split(";")[0].split("=")[1]
    )
    assert value == str(context.other.id), value


@then('the browser should not receive the cookie "{name}"')
def step_no_cookie(context, name):
    cookies = context.response.headers.get_list("set-cookie")
    assert not [c for c in cookies if c.startswith(f"{name}=")], cookies


# --- billing --------------------------------------------------------------------


def _plan(name, order, cents):
    return Plan(
        id=name.lower(),
        slug=name.lower(),
        name=name,
        description=f"{name} plan",
        features=[],
        limits=None,
        prices=[
            PlanPrice(
                id=f"price_{name.lower()}_month",
                currency="usd",
                unit_amount=cents,
                interval="month",
            )
        ],
        is_recommended=name == "Pro",
        sort_order=order,
    )


@given(
    'the billing client lists the plans "{first}" at {first_cents:d} cents and "{second}" at {second_cents:d} cents per month'
)
def step_plans(context, first, first_cents, second, second_cents):
    context.billing.plans = [_plan(first, 1, first_cents), _plan(second, 2, second_cents)]


@given("the billing client is failing")
def step_billing_failing(context):
    context.billing.error = BillingAPIError("billing is down")


@given("billing is not configured")
def step_billing_unconfigured(context):
    context.billing.is_configured = False


@given('the workspace has an active subscription "{subscription_id}"')
def step_subscription(context, subscription_id):
    context.billing.subscription = TenantSubscription(
        id=subscription_id,
        status="active",
        price_id="price_starter_month",
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC),
    )


@given('upgrading to "{price_id}" would cost {total:d} cents after a credit of {credit:d} cents')
def step_preview(context, price_id, total, credit):
    context.billing.preview = UpgradePreview(
        current_plan_name="Starter",
        new_plan_name="Pro",
        current_price_amount=900,
        new_price_amount=2900,
        line_items=[ProrationLineItem(description="Pro (remaining time)", amount=total + credit)],
        subtotal=total + credit,
        total=total,
        credit_applied=credit,
    )


@given("upgrades succeed")
def step_upgrades_succeed(context):
    context.billing.upgrade_result = UpgradeResult(
        success=True, proration_applied=True, amount_due=1500, invoice_id="in_1"
    )


@when('I choose the price "{price_id}"')
def step_choose_price(context, price_id):
    context.response = context.call(
        "POST", "/organizations/checkout", data={"price_id": price_id}, follow_redirects=False
    )


@when('I preview the upgrade to "{price_id}"')
def step_preview_upgrade(context, price_id):
    context.response = context.call(
        "GET", f"/organizations/upgrade/preview?price_id={price_id}", follow_redirects=False
    )


@when('I upgrade to "{price_id}"')
def step_upgrade(context, price_id):
    context.response = context.call(
        "POST", "/organizations/upgrade", data={"price_id": price_id}, follow_redirects=False
    )


@then(
    'the billing service should have created a checkout for the workspace "{name}" and the price "{price_id}"'
)
def step_checkout_created(context, name, price_id):
    call = context.billing.checkout_calls[0]
    assert call["tenant_id"] == str(context.tenant.id) and call["price_id"] == price_id
    assert call["customer_name"] == name


@then('the subscription "{subscription_id}" should have been upgraded to "{price_id}"')
def step_upgraded(context, subscription_id, price_id):
    call = context.billing.upgrade_calls[0]
    assert call["subscription_id"] == subscription_id and call["new_price_id"] == price_id


# --- settings -------------------------------------------------------------------


@when('I rename the workspace to "{name}"')
def step_rename(context, name):
    context.response = context.call(
        "POST", "/organizations/settings", data={"name": name}, follow_redirects=False
    )


@then('the workspace should be named "{name}"')
def step_named(context, name):
    assert context.tenant.name == name
