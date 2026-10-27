# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of the account and organisation settings."""

import asyncio
import hashlib
import hmac
import re
import threading
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pyotp
from auth.core.security import verify_password
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import Role, RoleScope, Scope, UserRole
from auth.db.models.tenant import IdentityProvider, Tenant, TenantCustomRole, TenantMember
from auth.db.models.user import UserEmail, UserProfile
from auth.services.pat import PAT_PREFIX
from auth.services.tenant_role import tenant_role_service
from auth.tasks import webhooks as webhook_tasks
from behave import given, then, when
from browser_support import mail_code
from e2e_support import behave_hooks as e2e
from factories import make_tenant
from helpers import patch_setting
from registration_steps import _email_row
from settings_pages_steps import _user
from sqlalchemy import select
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


@given('"{email}" signed in to the settings')
def step_signed_in(context, email):
    """Sign in on the login page, the way a user reaches the settings."""
    context.page.goto(f"{context.base_url}/auth/login?next=/auth/settings")
    context.page.get_by_label("Email").fill(email)
    context.page.get_by_label("Password").fill("Sup3r!secret")
    context.page.get_by_role("button", name="Login", exact=True).click()
    context.page.wait_for_url("**/auth/settings/**")


def _sidebar(context):
    return context.page.locator("aside.settings-sidebar")


@when('I open "{section}" from the settings menu')
@given('I open "{section}" from the settings menu')
def step_open_section(context, section):
    _sidebar(context).get_by_role("link", name=re.compile(rf"{re.escape(section)}$")).first.click()


@then('the settings menu marks "{section}" as the current section')
def step_current_section(context, section):
    link = _sidebar(context).locator("a.active")
    link.wait_for(state="visible")
    assert section in link.inner_text(), link.inner_text()


# A 1x1 PNG, the smallest image the upload service accepts.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


@when('I choose the avatar file "{name}" on the profile page')
def step_choose_avatar(context, name):
    context.page.locator("input[type=file]").first.set_input_files(
        files=[{"name": name, "mimeType": "image/png", "buffer": PNG}]
    )


@then('the stored profile of "{email}" has {field} "{value}"')
def step_stored_profile(context, email, field, value):
    context.database.sync_session.expire_all()
    row = _email_row(context, email)
    profile = context.database.sync_session.scalars(
        select(UserProfile).where(UserProfile.user_id == row.user_id)
    ).one()
    assert getattr(profile, field.replace(" ", "_")) == value, getattr(profile, field)


@when('I click the link named exactly "{name}"')
def step_click_link(context, name):
    context.page.get_by_role("link", name=name, exact=True).click()


@when('I enter the e-mailed code of "{email}" on the e-mails page')
def step_email_code(context, email):
    row = context.page.locator("div.email-item", has_text=email)
    row.locator("input[name=code]").fill(mail_code(context, email))


@given('the user "{email}" also has the verified address "{address}"')
def step_second_address(context, email, address):
    context.database.sync_session.add(
        UserEmail(
            user_id=_user(context, email).id, email=address, is_primary=False, is_verified=True
        )
    )
    context.database.commit()


@when('I enter "{code}" in the {form} form')
def step_enter_code(context, code, form):
    context.page.locator(f"#{form}-form input[name=code]").fill(code)


@when("I enter the current authenticator code in the {form} form")
def step_enter_current_code(context, form):
    code = pyotp.TOTP(context.totp_secret).now()
    context.page.locator(f"#{form}-form input[name=code]").fill(code)


@then("the security page lists {count:d} new backup codes")
def step_new_codes(context, count):
    items = context.page.locator("#new-backup-codes li")
    items.first.wait_for(state="visible")
    assert len(items.all_inner_texts()) == count


@given('"{email}" holds a role granting the scopes "{scopes}"')
def step_role_with_scopes(context, email, scopes):
    session = context.database.sync_session
    role = Role(name="reader", description="Reads", is_system=False)
    session.add(role)
    session.flush()
    for name in scopes.split():
        resource, _, action = name.partition(":")
        scope = Scope(name=name, resource=resource, action=action, category="api", is_system=False)
        session.add(scope)
        session.flush()
        session.add(RoleScope(role_id=role.id, scope_id=scope.id))
    session.add(UserRole(role_id=role.id, user_id=_user(context, email).id))
    context.database.commit()


@when('I tick the scope "{scope}" of the new token')
def step_tick_scope(context, scope):
    context.page.locator(f"#create-modal input[name=scopes][value='{scope}']").check()


def _displayed_token(context):
    token = context.page.locator("#new-token-value")
    token.wait_for(state="visible")
    return token.inner_text().strip()


@then("the token shown on the page starts with the personal access token prefix")
def step_token_prefix(context):
    context.token = _displayed_token(context)
    assert context.token.startswith(PAT_PREFIX), context.token


@then("the token shown on the page opens the users API")
def step_token_authenticates(context):
    context.token = _displayed_token(context)
    response = httpx.get(
        f"{context.base_url}/api/v1/users/", headers={"Authorization": f"Bearer {context.token}"}
    )
    assert response.status_code == 200, response.text


@then("the token of the page no longer opens the users API")
def step_token_revoked(context):
    deadline = time.monotonic() + context.e2e.settings.timeout / 1000
    while True:
        response = httpx.get(
            f"{context.base_url}/api/v1/users/",
            headers={"Authorization": f"Bearer {context.token}"},
        )
        if response.status_code == 401 or time.monotonic() > deadline:
            break
        context.page.wait_for_timeout(100)
    assert response.status_code == 401, response.status_code


@when('I open the organization "{name}" from the organizations page')
@given('I open the organization "{name}" from the organizations page')
def step_open_organization(context, name):
    context.page.goto(f"{context.base_url}/auth/settings/organisations")
    card = context.page.locator("div", has_text=name).filter(
        has=context.page.get_by_role("link", name="Manage")
    )
    card.last.get_by_role("link", name="Manage").click()


@given('"{email}" is the owner of the organization "{name}" with the slug "{slug}"')
def step_owner_of(context, email, name, slug):
    tenant = make_tenant(context.database.sync_session, slug)
    tenant.display_name = name
    context.database.commit()
    asyncio.run(tenant_role_service.create_default_roles(context.db, tenant))
    context.database.commit()
    owner = context.database.sync_session.scalars(
        select(TenantCustomRole).where(
            TenantCustomRole.tenant_id == tenant.id, TenantCustomRole.name == "owner"
        )
    ).one()
    context.database.sync_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=_user(context, email).id,
            role_id=owner.id,
            joined_at=datetime.now(UTC),
        )
    )
    context.database.commit()


@then('the tenant "{slug}" has a role "{name}"')
def step_tenant_role(context, slug, name):
    context.database.sync_session.expire_all()
    names = context.database.sync_session.scalars(
        select(TenantCustomRole.name)
        .join(Tenant, Tenant.id == TenantCustomRole.tenant_id)
        .where(Tenant.slug == slug)
    ).all()
    assert name in names, names


@when('I open "{path}" on the tenants server')
@given('I open "{path}" on the tenants server')
def step_open_on_tenants(context, path):
    context.page.goto(f"{context.tenant_url}{path}")


@when('I untick "{label}"')
def step_untick(context, label):
    context.page.get_by_label(label).first.uncheck()


@then('the page asks for "{label}"')
def step_page_asks(context, label):
    """The field is on the page, possibly in a section that is folded."""
    context.page.get_by_label(label).first.wait_for(state="attached")


@then('the page does not ask for "{label}"')
def step_page_does_not_ask(context, label):
    context.page.wait_for_load_state()
    assert context.page.get_by_label(label).count() == 0, label


@when('I set the colour field "{name}" to "{value}"')
def step_set_colour(context, name, value):
    context.page.locator(f"input[type=color][name={name}]").fill(value)


@then('the submit button of the page is outlined in "{colour}"')
def step_button_colour(context, colour):
    expected = tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))
    painted = context.page.locator("button[type=submit]").first.evaluate(
        "el => getComputedStyle(el).borderTopColor"
    )
    assert painted == f"rgb({expected[0]}, {expected[1]}, {expected[2]})", painted


@when('I tick the trust mode "{mode}"')
def step_trust_mode(context, mode):
    context.page.locator(f"input[type=radio][name=trust_mode][value={mode}]").check()


@given('"{email}" is a member of the organization "{slug}"')
def step_member_of(context, email, slug):
    tenant = context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()
    role = context.database.sync_session.scalars(
        select(TenantCustomRole).where(
            TenantCustomRole.tenant_id == tenant.id, TenantCustomRole.name == "member"
        )
    ).one()
    context.database.sync_session.add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=_user(context, email).id,
            role_id=role.id,
            joined_at=datetime.now(UTC),
        )
    )
    context.database.commit()


@then('the user "{email}" is no longer a member of the tenant "{slug}"')
def step_not_member(context, email, slug):
    context.database.sync_session.expire_all()
    found = context.database.sync_session.scalars(
        select(TenantMember)
        .join(Tenant, Tenant.id == TenantMember.tenant_id)
        .where(Tenant.slug == slug, TenantMember.user_id == _user(context, email).id)
    ).first()
    assert found is None


@then('the secret shown in the warning is the one of the client "{name}"')
def step_warning_secret(context, name):
    secret = context.page.locator("div.warning code").first.inner_text().strip()
    context.database.sync_session.expire_all()
    client = context.database.sync_session.scalars(
        select(OAuth2Client).where(OAuth2Client.name == name)
    ).one()
    assert verify_password(secret, client.client_secret_hash)


@given("a webhook receiver is listening and private networks are allowed")
def step_webhook_receiver(context):
    """A tiny HTTP endpoint on its own port, called by the delivery task like a real subscriber."""
    received = []

    async def hook(request):
        received.append({"headers": dict(request.headers), "body": await request.body()})
        return PlainTextResponse("ok")

    name = f"webhook receiver {uuid.uuid4().hex[:8]}"
    server = e2e.live_server(
        context, name, Starlette(routes=[Route("/hook", hook, methods=["POST"])])
    )
    context.add_cleanup(lambda: (server.stop(), context.e2e.servers.pop(name, None)))
    context.webhook_receiver = received
    context.webhook_receiver_url = f"{server.url}/hook"
    patch_setting(context, "webhook_allow_private_networks", True)

    # Run the task in this process instead of queueing it for a Celery worker, a moment after
    # the request has committed, as a worker picking it up from the queue would.
    def deliver_later(delivery_id):
        timer = threading.Timer(
            0.3, webhook_tasks.deliver_webhook.apply, kwargs={"args": [delivery_id]}
        )
        timer.start()
        context.add_cleanup(timer.cancel)

    patcher = patch.object(webhook_tasks.deliver_webhook, "delay", deliver_later)
    patcher.start()
    context.add_cleanup(patcher.stop)


@when('I fill "{label}" with the address of the webhook receiver')
def step_fill_receiver(context, label):
    context.page.get_by_label(label).first.fill(context.webhook_receiver_url)


@then("the signing secret of the webhook is shown")
def step_webhook_secret_shown(context):
    field = context.page.locator("input[id^=new-webhook-secret]")
    field.wait_for(state="visible")
    context.webhook_secret = field.input_value()
    assert context.webhook_secret


@then('the receiver was called with a "{event}" event signed with that secret')
def step_receiver_called(context, event):
    deadline = time.monotonic() + context.e2e.settings.timeout / 1000
    while not context.webhook_receiver and time.monotonic() < deadline:
        context.page.wait_for_timeout(50)
    assert context.webhook_receiver, "the receiver was not called"
    call = context.webhook_receiver[-1]
    assert call["headers"]["x-webhook-event"] == event
    timestamp = call["headers"]["x-webhook-timestamp"]
    digest = hmac.new(
        context.webhook_secret.encode(), timestamp.encode() + b"." + call["body"], hashlib.sha256
    ).hexdigest()
    assert call["headers"]["x-webhook-signature"] == f"t={timestamp},v1={digest}"


def _identity_provider(context, name):
    context.database.sync_session.expire_all()
    return context.database.sync_session.scalars(
        select(IdentityProvider).where(IdentityProvider.name == name)
    ).one()


@then('the identity provider "{name}" is switched off in the database')
def step_idp_off(context, name):
    assert _identity_provider(context, name).is_active is False


@then('the identity provider "{name}" is active in the database')
def step_idp_on(context, name):
    assert _identity_provider(context, name).is_active is True
