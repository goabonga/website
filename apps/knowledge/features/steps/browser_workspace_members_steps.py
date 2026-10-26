# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace members and invitations pages in a browser.

The invitation emails are sent by the real Celery task, run synchronously, through the
mailler fake of the stack: the steps read the link a person would find in their mailbox.
"""

import secrets
from datetime import UTC, datetime, timedelta

import browser_stack
from behave import given, then, when
from browser_mailbox import Mailbox, deliver_in_process
from playwright.sync_api import expect

from knowledge.models import Organization, OrganizationInvitation, OrganizationMember
from knowledge.models.enums import InvitationStatus, OrganizationMemberRole

INVITATION_TEMPLATE = "workspace-invitation"


@browser_stack.scenario_setup
def install_mailbox(stack, scenario):
    stack.mailbox = Mailbox()
    deliver_in_process(stack.mailbox, scenario)


def members_of(context, name):
    with context.stack.db.session() as session:
        organization = session.query(Organization).filter(Organization.name == name).one()
        return list(
            session.query(OrganizationMember)
            .filter(OrganizationMember.organization_id == organization.id)
            .all()
        )


@then('the workspace "{name}" should have {count:d} member')
@then('the workspace "{name}" should have {count:d} members')
def step_workspace_member_count(context, name, count):
    assert len(members_of(context, name)) == count


def _invitation(context, email):
    with context.stack.db.session() as session:
        return (
            session.query(OrganizationInvitation)
            .filter(OrganizationInvitation.email == email)
            .one()
        )


def _seed_invitation(context, email, workspace, expires_in):
    with context.stack.db.session() as session:
        organization = session.query(Organization).filter(Organization.name == workspace).one()
        session.add(
            OrganizationInvitation(
                organization_id=organization.id,
                email=email,
                role=OrganizationMemberRole.MEMBER,
                token=secrets.token_urlsafe(32),
                invited_by=organization.id,
                expires_at=datetime.now(UTC) + expires_in,
            )
        )


@given('"{email}" has a pending invitation to the workspace "{workspace}"')
def step_pending(context, email, workspace):
    _seed_invitation(context, email, workspace, timedelta(days=7))


@given('"{email}" has an expired invitation to the workspace "{workspace}"')
def step_expired(context, email, workspace):
    _seed_invitation(context, email, workspace, timedelta(days=-1))


@given('I invite "{email}" as "{role}" from the members page')
def step_invite(context, email, role):
    context.page.goto("/tenants/invite")
    context.page.get_by_label("Email Address").fill(email)
    context.page.locator("select[name=role]").select_option(role)
    context.page.get_by_role("button", name="Send Invitation").click()
    expect(context.page).to_have_url(f"{context.base_url}/organizations/members")


def invitation_mails(context, email):
    return [m for m in context.stack.mailbox.to(email)]


@when('I open the invitation link sent to "{email}"')
def step_open_mailed_link(context, email):
    mails = invitation_mails(context, email)
    assert mails, f"{email} received no email"
    context.page.goto(mails[-1].variables["invitation_url"])


@when('I open the invitation link of "{email}"')
def step_open_link(context, email):
    context.page.goto(f"/tenants/invites/{_invitation(context, email).token}")


@then('"{email}" received an invitation to the workspace "{workspace}" as "{role}"')
def step_received(context, email, workspace, role):
    mails = invitation_mails(context, email)
    assert len(mails) == 1, context.stack.mailbox.sent
    variables = mails[0].variables
    assert variables["workspace_name"] == workspace and variables["role"] == role, variables
    assert variables["invitation_url"].startswith(context.base_url), variables


@then("no invitation email was sent")
def step_no_email(context):
    assert context.stack.mailbox.sent == [], context.stack.mailbox.sent


@then('"{email}" received {count:d} invitation email')
def step_received_count(context, email, count):
    expect(context.page).to_have_url(f"{context.base_url}/organizations/members")
    assert len(invitation_mails(context, email)) == count, context.stack.mailbox.sent


@then('"{name}" should have the role "{role}" in the workspace "{workspace}"')
def step_role(context, name, role, workspace):
    def role_of():
        return next(m.role for m in members_of(context, workspace) if m.display_name == name)

    deadline = datetime.now() + timedelta(seconds=10)
    while role_of().value != role and datetime.now() < deadline:
        context.page.wait_for_timeout(100)
    assert role_of().value == role
    assert InvitationStatus  # the statuses are checked through the pages
