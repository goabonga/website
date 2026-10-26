# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the workspace members and invitations pages.

Routes and templates are real. Invitation emails are queued through a recording
stand-in for the Celery task, and token validation for the public pages is a
fake validator.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

from behave import given, then, when

from knowledge.models import OrganizationInvitation, OrganizationMember
from knowledge.models.enums import InvitationStatus, OrganizationMemberRole

BASE = "/organizations"


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("invitation emails are queued in memory")
def step_emails_in_memory(context):
    context.queued_emails = []
    _patch(
        context,
        "knowledge.tasks.send_workspace_invitation_email.delay",
        lambda **kwargs: context.queued_emails.append(kwargs),
    )


def _add_member(context, email, role):
    member = OrganizationMember(
        id=uuid4(),
        organization_id=context.tenant.id,
        user_id=uuid4(),
        role=OrganizationMemberRole(role),
        email=email,
        created_at=datetime.now(UTC),
    )
    context.store.members[member.id] = member
    return member


def _member(context, email):
    return next(m for m in context.store.members.values() if m.email == email)


def _add_invitation(context, email, role="member", expires_in=timedelta(days=7)):
    invitation = OrganizationInvitation(
        id=uuid4(),
        organization_id=context.tenant.id,
        email=email,
        role=OrganizationMemberRole(role),
        token=f"token-{email.split('@')[0]}",
        status=InvitationStatus.PENDING,
        invited_by=context.member.user_id,
        expires_at=datetime.now(UTC) + expires_in,
        created_at=datetime.now(UTC),
    )
    context.store.org_invitations[invitation.id] = invitation
    return invitation


def _invitation(context, email):
    return next(i for i in context.store.org_invitations.values() if i.email == email)


@given('"{email}" is a member of the workspace with the role "{role}"')
def step_member(context, email, role):
    _add_member(context, email, role)


@given('"{email}" has a pending invitation')
def step_pending_invitation(context, email):
    _add_invitation(context, email)


@given('"{email}" has a pending invitation with the role "{role}"')
def step_pending_invitation_with_role(context, email, role):
    _add_invitation(context, email, role)


@given('"{email}" has an expired invitation')
def step_expired_invitation(context, email):
    _add_invitation(context, email, expires_in=timedelta(days=-1))


@given('the invitation of "{email}" is revoked')
def step_revoked_invitation(context, email):
    _invitation(context, email).status = InvitationStatus.REVOKED


# --- administration ------------------------------------------------------------


@when('I invite "{email}" as "{role}"')
def step_invite(context, email, role):
    context.response = context.call(
        "POST", f"{BASE}/invite", data={"email": email, "role": role}, follow_redirects=False
    )


@when('I resend the invitation of "{email}"')
def step_resend(context, email):
    context.response = context.call(
        "POST",
        f"{BASE}/invitations/{_invitation(context, email).id}/resend",
        follow_redirects=False,
    )


@when('I revoke the invitation of "{email}"')
def step_revoke(context, email):
    context.response = context.call(
        "POST",
        f"{BASE}/invitations/{_invitation(context, email).id}/revoke",
        follow_redirects=False,
    )


@when('I change the role of "{email}" to "{role}"')
def step_change_role(context, email, role):
    context.response = context.call(
        "POST",
        f"{BASE}/members/{_member(context, email).id}/role",
        data={"role": role},
        follow_redirects=False,
    )


@when('I change my own role to "{role}"')
def step_change_own_role(context, role):
    context.response = context.call(
        "POST",
        f"{BASE}/members/{context.member.id}/role",
        data={"role": role},
        follow_redirects=False,
    )


@when('I remove "{email}" from the workspace')
def step_remove(context, email):
    context.response = context.call(
        "POST", f"{BASE}/members/{_member(context, email).id}/remove", follow_redirects=False
    )


@then('the workspace should hold a pending "{role}" invitation for "{email}"')
def step_holds_invitation(context, role, email):
    invitation = _invitation(context, email)
    assert invitation.status == InvitationStatus.PENDING
    assert invitation.role == OrganizationMemberRole(role)
    assert invitation.organization_id == context.tenant.id


@then('an invitation email should be queued for "{email}" mentioning the workspace "{name}"')
def step_email_queued(context, email, name):
    assert context.queued_emails, "no email queued"
    email_kwargs = context.queued_emails[-1]
    assert email_kwargs["to"] == email and email_kwargs["workspace_name"] == name
    assert email_kwargs["invitation_url"].endswith(_invitation(context, email).token)


@then("no invitation email should be queued")
def step_no_email(context):
    assert context.queued_emails == []


@then('the invitation of "{email}" should be "{status}"')
def step_invitation_status(context, email, status):
    assert _invitation(context, email).status == InvitationStatus(status)


@then('"{email}" should have the role "{role}"')
def step_has_role(context, email, role):
    assert _member(context, email).role == OrganizationMemberRole(role)


@then('I should still be an "{role}"')
def step_still_role(context, role):
    assert context.member.role == OrganizationMemberRole(role)


@then('"{email}" should no longer be a member')
def step_not_member(context, email):
    assert email not in [m.email for m in context.store.members.values()]


# --- public invitation pages ---------------------------------------------------


@when('a visitor opens the invitation of "{email}"')
def step_visitor_opens(context, email):
    context.response = context.call(
        "GET", f"{BASE}/invites/{_invitation(context, email).token}", follow_redirects=False
    )


@when('a visitor opens the invitation token "{token}"')
def step_visitor_opens_token(context, token):
    context.response = context.call("GET", f"{BASE}/invites/{token}", follow_redirects=False)


@when('a visitor accepts the invitation of "{email}"')
def step_visitor_accepts(context, email):
    context.response = context.call(
        "POST", f"{BASE}/invites/{_invitation(context, email).token}/accept", follow_redirects=False
    )


class _Validator:
    def __init__(self, user_id):
        self.user_id = user_id

    async def validate_token_with_introspection(self, token, **kwargs):
        return {"sub": self.user_id, "name": "Newcomer"}


@when('the user "{user_id}" accepts the invitation of "{email}"')
def step_user_accepts(context, user_id, email):
    _patch(context, "knowledge.auth.jwt.get_jwt_validator", lambda: _Validator(user_id))
    context.response = context.call(
        "POST",
        f"{BASE}/invites/{_invitation(context, email).token}/accept",
        headers={"Cookie": "access_token=valid"},
        follow_redirects=False,
    )


@then('the user "{user_id}" should be an "{role}" of the workspace')
def step_user_is_member(context, user_id, role):
    members = [
        m
        for m in context.store.members.values()
        if m.user_id == UUID(user_id) and m.organization_id == context.tenant.id
    ]
    assert [m.role for m in members] == [OrganizationMemberRole(role)], members
