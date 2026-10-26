# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace deletion flow.

Routes, templates and the deletion request model are real. The database is the
in-memory store, emails are queued in recording stand-ins and the billing
service is the configurable fake.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from behave import given, then, when

from knowledge.models import WorkspaceDeletionRequest
from knowledge.models.workspace_deletion_request import DeletionRequestStatus
from knowledge.services.billing import TenantSubscription


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("deletion emails are queued in memory")
def step_emails_in_memory(context):
    context.deletion_emails = {}
    for kind, task in (
        ("confirmation", "send_workspace_deletion_email"),
        ("scheduled", "send_workspace_deletion_scheduled_email"),
        ("deleted", "send_workspace_deleted_email"),
    ):
        _patch(
            context,
            f"knowledge.tasks.{task}.delay",
            lambda kind=kind, **kwargs: context.deletion_emails.setdefault(kind, []).append(kwargs),
        )


def _new_request(context, status, expires_in=timedelta(hours=24), scheduled_in=None):
    request = WorkspaceDeletionRequest(
        id=uuid4(),
        organization_id=context.tenant.id,
        requested_by=context.member.user_id,
        email="alice@example.test",
        token=WorkspaceDeletionRequest.generate_token(),
        status=status,
        expires_at=datetime.now(UTC) + expires_in,
        created_at=datetime.now(UTC),
        subscription_cancelled=scheduled_in is not None,
    )
    if scheduled_in is not None:
        request.scheduled_deletion_at = datetime.now(UTC) + scheduled_in
        request.cancel_token = WorkspaceDeletionRequest.generate_token()
    context.store.deletion_requests[request.id] = request
    context.deletion_request = request
    return request


@given("a pending deletion request exists for the workspace")
def step_pending_request(context):
    _new_request(context, DeletionRequestStatus.PENDING)


@given("an expired deletion request exists for the workspace")
def step_expired_request(context):
    _new_request(context, DeletionRequestStatus.PENDING, expires_in=timedelta(hours=-1))


@given("a scheduled deletion request exists for the workspace")
def step_scheduled_request(context):
    _new_request(context, DeletionRequestStatus.SCHEDULED, scheduled_in=timedelta(days=20))


@given("a deletion request that was already carried out exists for the workspace")
def step_carried_out_request(context):
    _new_request(context, DeletionRequestStatus.CONFIRMED, scheduled_in=timedelta(days=-1))


@given('the workspace has a subscription "{subscription_id}" renewing in {days:d} days')
def step_subscription(context, subscription_id, days):
    context.billing.subscription = TenantSubscription(
        id=subscription_id,
        status="active",
        price_id="price_pro_month",
        current_period_start=datetime.now(UTC) - timedelta(days=10),
        current_period_end=datetime.now(UTC) + timedelta(days=days),
        cancel_at_period_end=True,
    )


@when('I request the deletion of the workspace typing "{name}"')
def step_request_deletion(context, name):
    context.response = context.call(
        "POST", "/organizations/delete", data={"confirmation_name": name}, follow_redirects=False
    )


@when("I open the deletion confirmation page")
def step_open_confirmation(context):
    context.response = context.call(
        "GET",
        f"/organizations/delete/confirm/{context.deletion_request.token}",
        follow_redirects=False,
    )


@when("I confirm the deletion")
def step_confirm_deletion(context):
    context.response = context.call(
        "POST",
        f"/organizations/delete/confirm/{context.deletion_request.token}",
        follow_redirects=False,
    )


@when("I open the cancellation link")
def step_open_cancellation(context):
    context.response = context.call(
        "GET",
        f"/organizations/delete/cancel/{context.deletion_request.cancel_token}",
        follow_redirects=False,
    )


def _requests(context):
    return list(context.store.deletion_requests.values())


@then("no deletion request should exist")
def step_no_request(context):
    assert _requests(context) == []


@then("a pending deletion request should exist")
def step_pending_exists(context):
    pending = [r for r in _requests(context) if r.status == DeletionRequestStatus.PENDING]
    assert len(pending) == 1 and pending[0].organization_id == context.tenant.id
    context.deletion_request = pending[0]


@then("a confirmation email should be queued with a link to the confirmation page")
def step_confirmation_email(context):
    emails = context.deletion_emails["confirmation"]
    assert len(emails) == 1
    assert emails[0]["confirmation_url"].endswith(
        f"/organizations/delete/confirm/{context.deletion_request.token}"
    )
    assert emails[0]["workspace_name"] == context.tenant.name


@then('{count:d} deletion request should be "{status}"')
def step_request_status_count(context, count, status):
    matching = [r for r in _requests(context) if r.status == DeletionRequestStatus(status)]
    assert len(matching) == count, [r.status for r in _requests(context)]


@then('the workspace "{name}" should no longer exist')
def step_workspace_gone(context, name):
    assert name not in [o.name for o in context.store.organizations.values()]


@then('the workspace "{name}" should still exist')
def step_workspace_exists(context, name):
    assert name in [o.name for o in context.store.organizations.values()]


@then('a "{kind}" email should be queued')
def step_email_kind(context, kind):
    assert len(context.deletion_emails.get(kind, [])) == 1, context.deletion_emails


@then('the subscription "{subscription_id}" should have been set to cancel at period end')
def step_cancelled(context, subscription_id):
    args, kwargs = context.billing.cancel_calls[0]
    assert kwargs["subscription_id"] == subscription_id and kwargs["cancel_at_period_end"] is True


@then('the subscription "{subscription_id}" should have been reactivated')
def step_reactivated(context, subscription_id):
    args, kwargs = context.billing.reactivate_calls[0]
    assert kwargs["subscription_id"] == subscription_id
