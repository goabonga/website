# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace switching, plan upgrade and settings pages in a browser.

The billing service is the fake of the stack: the checkout it creates sends the customer
straight back to the success address, as a customer who paid would be, and the proration
quotes and subscriptions are what the scenario declares.
"""

import re
from datetime import UTC, datetime
from unittest.mock import patch

import browser_stack
from behave import given, then
from playwright.sync_api import expect

from knowledge.services.billing import (
    ProrationLineItem,
    TenantSubscription,
    UpgradePreview,
    UpgradeResult,
)


@browser_stack.scenario_setup
def install_workspace_billing(stack, scenario):
    scenario.enter_context(
        patch("knowledge.routes.web.organizations.get_billing_client", lambda: stack.billing)
    )
    scenario.enter_context(
        browser_stack.patch_setting(
            "billing_checkout_success_url", f"{stack.url}/tenants/pricing?success=true"
        )
    )
    scenario.enter_context(
        browser_stack.patch_setting(
            "billing_checkout_cancel_url", f"{stack.url}/tenants/pricing?cancelled=true"
        )
    )


@given('the billing service holds the subscription "{subscription_id}" of the workspace')
def step_subscription(context, subscription_id):
    now = datetime.now(UTC)
    context.stack.billing.subscription = TenantSubscription(
        id=subscription_id,
        status="active",
        price_id="Starter-month",
        current_period_start=now,
        current_period_end=now,
    )


@given(
    "the billing service quotes {total:d} cents for the upgrade after a credit of {credit:d} cents"
)
def step_quote(context, total, credit):
    context.stack.billing.preview = UpgradePreview(
        current_plan_name="Starter",
        new_plan_name="Pro",
        current_price_amount=900,
        new_price_amount=2900,
        line_items=[ProrationLineItem(description="Pro (remaining time)", amount=total + credit)],
        subtotal=total + credit,
        total=total,
        credit_applied=credit,
    )


@given("the billing service accepts the upgrades")
def step_accepts_upgrades(context):
    context.stack.billing.upgrade_result = UpgradeResult(
        success=True, proration_applied=True, amount_due=1500, invoice_id="in_1"
    )


@then('the workspace switcher should show "{name}"')
def step_switcher(context, name):
    expect(context.page.locator("select[name=tenant_id] option:checked")).to_have_text(
        name, use_inner_text=True
    )


@then('the billing service created a checkout for the workspace "{name}" and the price "{price}"')
def step_checkout(context, name, price):
    calls = context.stack.billing.checkout_calls
    assert calls, "no checkout was created"
    assert calls[-1]["price_id"] == price and calls[-1]["customer_name"] == name, calls[-1]


@then('the subscription "{subscription_id}" was upgraded to the price "{price}"')
def step_upgraded(context, subscription_id, price):
    calls = context.stack.billing.upgrade_calls
    assert calls and calls[-1]["subscription_id"] == subscription_id, calls
    assert calls[-1]["new_price_id"] == price, calls[-1]


@then("the billing service made no upgrade")
def step_no_upgrade(context):
    assert context.stack.billing.upgrade_calls == []


@then('the dashboard should show the plan "{plan}"')
def step_plan(context, plan):
    card = context.page.locator(".stat-card", has=context.page.get_by_text("Plan", exact=True))
    expect(card.locator(".stat-value")).to_have_text(re.compile(f"^{plan}$", re.IGNORECASE))
