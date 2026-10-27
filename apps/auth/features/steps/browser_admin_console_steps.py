# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of the administration console."""

import re
from urllib.parse import urlsplit

import httpx
from admin_console_steps import _user
from auth.core.security import verify_password
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.rbac import Role, UserRole
from behave import given, then, when
from sqlalchemy import select


@given('"{email}" signed in to the administration console')
def step_admin_signs_in(context, email):
    """Sign in on the login page, the way an administrator reaches the console."""
    context.page.goto(f"{context.base_url}/auth/login?next=/admin/")
    context.page.get_by_label("Email").fill(email)
    context.page.get_by_label("Password").fill("Sup3r!secret")
    context.page.get_by_role("button", name="Login", exact=True).click()
    context.page.wait_for_url("**/admin/")


def _sidebar_link(context, section):
    """The sidebar link whose label ends with the section name (an icon comes first)."""
    return (
        context.page.locator("aside.admin-sidebar")
        .get_by_role("link", name=re.compile(rf"{re.escape(section)}$"))
        .first
    )


@when('I open "{section}" from the sidebar')
@given('I open "{section}" from the sidebar')
def step_open_section(context, section):
    _sidebar_link(context, section).click()


@then('the sidebar lists "{section}"')
def step_sidebar_lists(context, section):
    _sidebar_link(context, section).wait_for(state="visible")


@then('the sidebar does not list "{section}"')
def step_sidebar_does_not_list(context, section):
    context.page.locator("aside.admin-sidebar").wait_for(state="visible")
    assert _sidebar_link(context, section).count() == 0, f"the sidebar lists {section!r}"


@then('the sidebar marks "{section}" as the current section')
def step_sidebar_current(context, section):
    link = context.page.locator("aside.admin-sidebar a.active")
    link.wait_for(state="visible")
    assert section in link.inner_text(), link.inner_text()


@when('I click "{label}" in the row of "{text}"')
def step_click_in_row(context, label, text):
    row = context.page.locator("tr", has_text=text).first
    row.get_by_role("button", name=label).or_(row.get_by_role("link", name=label)).first.click()


@then('the row of "{text}" mentions "{expected}"')
def step_row_mentions(context, text, expected):
    row = context.page.locator("tr", has_text=text).first
    row.wait_for(state="visible")
    assert expected in row.inner_text(), row.inner_text()


@when('I choose the row of "{text}"')
def step_choose_row(context, text):
    """Tick the radio button or checkbox that has no label of its own in the row."""
    context.page.locator("tr", has_text=text).first.locator("input").first.check()


@when('I navigate to the edit page of the role "{name}"')
def step_navigate_role_edit(context, name):
    role = context.database.sync_session.scalars(select(Role).where(Role.name == name)).one()
    context.page.goto(f"{context.base_url}/admin/roles/{role.id}/edit")


@then('the user "{email}" has the role "{role}" in the database')
def step_user_has_role(context, email, role):
    context.database.sync_session.expire_all()
    names = context.database.sync_session.scalars(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == _user(context, email).id)
    ).all()
    assert role in names, names


def _client(context, name):
    context.database.sync_session.expire_all()
    return context.database.sync_session.scalars(
        select(OAuth2Client).where(OAuth2Client.name == name)
    ).one()


@then('the client "{name}" exists in the database')
def step_client_exists(context, name):
    assert _client(context, name).is_active


@then('the secret shown on the page is the one of the client "{name}"')
def step_secret_is_clients(context, name):
    secret = context.page.locator("code.mono").first.inner_text().strip()
    assert verify_password(secret, _client(context, name).client_secret_hash)


@when('I click the button named exactly "{name}"')
@given('I click the button named exactly "{name}"')
def step_click_exact(context, name):
    context.page.get_by_role("button", name=name, exact=True).click()


@when('I tick the box "{label}"')
def step_tick_box(context, label):
    context.page.get_by_label(label).check()


@then("the published key set lists the key shown on the page")
def step_published_key(context):
    kid = urlsplit(context.page.url).path.rstrip("/").rsplit("/", 1)[-1]
    keys = httpx.get(f"{context.base_url}/.well-known/jwks.json").json()["keys"]
    assert kid in [key["kid"] for key in keys], (kid, keys)


@when('I fill "{label}" with the client id of the external identity provider')
def step_fill_client_id(context, label):
    context.page.get_by_label(label).first.fill(context.idp_client_id)


@when('I fill "{label}" with the client secret of the external identity provider')
def step_fill_client_secret(context, label):
    context.page.get_by_label(label).first.fill(context.idp_client_secret)


@when('I fill "{label}" with the discovery address of the external identity provider')
def step_fill_discovery(context, label):
    context.page.get_by_label(label).first.fill(
        f"{context.idp_url}/.well-known/openid-configuration"
    )
