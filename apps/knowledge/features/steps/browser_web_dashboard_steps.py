# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the landing, dashboard, pricing and download pages in a browser.

The billing service is the in-memory fake of the stack; the MCP binaries are served by a
stand-in for the release host that the browser reaches through a route.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import browser_stack
from behave import given, then, when
from browser_billing import Billing
from playwright.sync_api import expect

from knowledge.models import McpRelease, McpReleaseAsset
from knowledge.models.enums import Platform, ReleaseStatus
from knowledge.services.billing import BillingAPIError, Plan, PlanPrice

#: Where the assets of a release are hosted (GitHub in production): any page of the
#: application will do, the scenarios only check that the browser is sent there.
RELEASE_ASSET_PATH = "/health"


@browser_stack.scenario_setup
def install_billing(stack, scenario):
    stack.billing = Billing()
    scenario.enter_context(
        patch("knowledge.routes.web.home.get_billing_client", lambda: stack.billing)
    )
    for name, value in (
        ("operator_name", "Example Operator"),
        ("contact_email", "contact@example.test"),
        ("legal_email", "legal@example.test"),
        ("privacy_email", "privacy@example.test"),
        ("sales_email", "sales@example.test"),
    ):
        scenario.enter_context(browser_stack.patch_setting(name, value))


# --- pricing -----------------------------------------------------------------------------


@given(
    'the billing service offers the plan "{name}" at {monthly:d} cents a month '
    "or {yearly:d} cents a year"
)
def step_plan(context, name, monthly, yearly):
    plans = context.stack.billing.plans
    plans.append(
        Plan(
            id=name.lower(),
            slug=name.lower(),
            name=name,
            description=f"The {name} plan",
            features=[],
            limits=None,
            prices=[
                PlanPrice(f"{name}-month", "usd", monthly, "month"),
                PlanPrice(f"{name}-year", "usd", yearly, "year"),
            ],
            is_recommended=len(plans) == 1,
            sort_order=len(plans),
        )
    )


@given("the billing service refuses every request")
def step_billing_failing(context):
    context.stack.billing.error = BillingAPIError("billing is down")


# --- dashboard ---------------------------------------------------------------------------


@then("the dashboard should display {collections:d} collections and {documents:d} documents")
def step_counts(context, collections, documents):
    values = context.page.locator(".stats-grid .stat-card .stat-value")
    expect(values.nth(0)).to_have_text(str(collections))
    expect(values.nth(1)).to_have_text(str(documents))


# --- downloads ---------------------------------------------------------------------------


@given('the release "{version}" is published with a binary for "{platform}"')
def step_release(context, version, platform):
    with context.stack.db.session() as session:
        release = McpRelease(
            version=version,
            github_release_id=1,
            status=ReleaseStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        session.add(release)
        session.flush()
        session.add(
            McpReleaseAsset(
                release_id=release.id,
                platform=Platform(platform),
                filename=f"knowledge-mcp-{version}-{platform}",
                download_url=f"{context.base_url}{RELEASE_ASSET_PATH}",
                file_size=1024,
            )
        )


@when('I download the "{platform}" binary')
def step_download(context, platform):
    link = context.page.locator(f"a[href$='/{platform}']").first
    with context.page.expect_navigation():
        link.click()


@then("the browser should be sent to the release host")
def step_sent_to_host(context):
    expect(context.page).to_have_url(f"{context.base_url}{RELEASE_ASSET_PATH}")


@then('the release "{version}" was downloaded {count:d} time for "{platform}"')
def step_download_count(context, version, count, platform):
    with context.stack.db.session() as session:
        asset = (
            session.query(McpReleaseAsset)
            .join(McpRelease)
            .filter(McpRelease.version == version, McpReleaseAsset.platform == Platform(platform))
            .one()
        )
        assert asset.download_count == count
