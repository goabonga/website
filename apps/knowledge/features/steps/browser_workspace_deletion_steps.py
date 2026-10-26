# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace deletion flow in a browser.

The three emails of the flow (confirmation, scheduled, deleted) are sent by the real Celery
tasks through the mailler fake of the stack; the steps follow the link of the confirmation
email like its recipient does.
"""

from datetime import UTC, datetime, timedelta

from behave import given, then, when
from playwright.sync_api import expect

from knowledge import email_templates
from knowledge.models import Organization
from knowledge.services.billing import TenantSubscription


def _mails(context, template):
    return [m for m in context.stack.mailbox.sent if m.template == template]


@given(
    'the billing service holds the subscription "{subscription_id}" '
    "of the workspace until the end of the period"
)
def step_subscription(context, subscription_id):
    now = datetime.now(UTC)
    context.stack.billing.subscription = TenantSubscription(
        id=subscription_id,
        status="active",
        price_id="Pro-month",
        current_period_start=now - timedelta(days=10),
        current_period_end=now + timedelta(days=20),
    )


@given('I request the deletion of the workspace "{name}"')
def step_request_deletion(context, name):
    page = context.page
    page.goto("/tenants/settings")
    page.get_by_role("button", name="Delete Workspace").click()
    page.get_by_placeholder("Type workspace name to confirm").fill(name)
    page.get_by_role("button", name="Send Confirmation Email").click()
    expect(page.get_by_text("Confirmation Email Sent")).to_be_visible()


@when('I open the deletion link sent to "{email}"')
def step_open_deletion_link(context, email):
    mails = [m for m in _mails(context, email_templates.WORKSPACE_DELETION) if m.to == email]
    assert mails, f"{email} received no deletion email"
    context.page.goto(mails[-1].variables["confirmation_url"])


@then('"{email}" received the deletion confirmation for the workspace "{name}"')
def step_confirmation_mail(context, email, name):
    mails = [m for m in _mails(context, email_templates.WORKSPACE_DELETION) if m.to == email]
    assert len(mails) == 1, context.stack.mailbox.sent
    variables = mails[0].variables
    assert variables["workspace_name"] == name, variables
    assert variables["confirmation_url"].startswith(context.base_url), variables


@then('"{email}" received the notice that the workspace "{name}" was deleted')
def step_deleted_mail(context, email, name):
    mails = [m for m in _mails(context, email_templates.WORKSPACE_DELETED) if m.to == email]
    assert [m.variables["workspace_name"] for m in mails] == [name], context.stack.mailbox.sent


@then('"{email}" received the notice that the deletion of "{name}" is scheduled')
def step_scheduled_mail(context, email, name):
    mails = [
        m for m in _mails(context, email_templates.WORKSPACE_DELETION_SCHEDULED) if m.to == email
    ]
    assert [m.variables["workspace_name"] for m in mails] == [name], context.stack.mailbox.sent


@then("no deletion email was sent")
def step_no_mail(context):
    assert context.stack.mailbox.sent == [], context.stack.mailbox.sent


@then('the workspace "{name}" should have been removed from the database')
def step_gone(context, name):
    with context.stack.db.session() as session:
        assert session.query(Organization).filter(Organization.name == name).count() == 0


@then('the billing service cancelled the subscription "{subscription_id}" at the end of the period')
def step_cancelled(context, subscription_id):
    calls = context.stack.billing.cancel_calls
    assert calls and calls[-1][1]["subscription_id"] == subscription_id, calls
    assert calls[-1][1]["cancel_at_period_end"] is True, calls
