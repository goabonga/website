# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the ``@browser`` scenarios: signing in, signing out, the cookies."""

import re
import uuid

import browser_support
from behave import given, then, when
from e2e_support import steps  # noqa: F401
from e2e_support.oidc import User
from playwright.sync_api import expect

#: A public page the scenarios land on after signing in, whatever the scopes of the user.
LANDING = "/health"


class Dialogs:
    """What the page asked through ``confirm(...)`` and the answer to give.

    Confirmations are accepted, like an operator clicking OK, unless the scenario said
    it dismisses the next one.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.dismiss_next = False

    def handle(self, dialog) -> None:
        self.messages.append(dialog.message)
        if self.dismiss_next:
            self.dismiss_next = False
            dialog.dismiss()
        else:
            dialog.accept()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "none"


def add_user(context, scopes: list[str], name: str = "Browser Admin") -> User:
    """Register a user holding ``scopes`` at the fake provider."""
    user = User(
        email=f"{_slug(' '.join(scopes))}-{uuid.uuid4().hex[:8]}@example.test",
        name=name,
        password=browser_support.USER_PASSWORD,
        scopes=tuple(scopes),
    )
    browser_support.provider(context).add_user(user)
    context.browser_user = user
    return user


def log_in_at_provider(context, email: str, password: str = browser_support.USER_PASSWORD) -> None:
    """Fill in the login form of the fake provider and submit it."""
    page = context.page
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


def sign_in(context, scopes: list[str], name: str = "Browser Admin") -> User:
    """Log a new user holding ``scopes`` in through the application's login route."""
    user = add_user(context, scopes, name)
    context.dialogs = Dialogs()
    context.page.on("dialog", context.dialogs.handle)
    context.page.goto(f"{context.base_url}/auth/login?redirect={LANDING}")
    log_in_at_provider(context, user.email)
    expect(context.page).to_have_url(f"{context.base_url}{LANDING}")
    return user


@given('I sign in with the scopes "{scopes}"')
def step_sign_in_with_scopes(context, scopes):
    sign_in(context, scopes.split())


@given("I sign in as a super administrator")
def step_sign_in_super_admin(context):
    sign_in(context, ["*"])


@given("I sign in with no scope")
def step_sign_in_without_scope(context):
    sign_in(context, [])


@given('I sign in as "{name}" with the scopes "{scopes}"')
def step_sign_in_named(context, name, scopes):
    sign_in(context, scopes.split(), name)


@when("I sign out")
def step_sign_out(context):
    context.page.goto(f"{context.base_url}/auth/logout?redirect={LANDING}")


def _cookie(context, name):
    return next((c for c in context.browser_context.cookies() if c["name"] == name), None)


@then('the cookie "{name}" should be set')
def step_cookie_set(context, name):
    assert _cookie(context, name) is not None, f"no cookie {name!r}"


@then('the cookie "{name}" should not be set')
def step_cookie_not_set(context, name):
    assert _cookie(context, name) is None, f"unexpected cookie {name!r}"


@then('the cookie "{name}" should be http only')
def step_cookie_http_only(context, name):
    cookie = _cookie(context, name)
    assert cookie is not None and cookie["httpOnly"], f"cookie {name!r} is not http only: {cookie}"


@then('the cookie "{name}" should be readable by scripts')
def step_cookie_script_readable(context, name):
    cookie = _cookie(context, name)
    assert cookie is not None and not cookie["httpOnly"], f"cookie {name!r}: {cookie}"


@then('the cookie "{name}" should have the SameSite policy "{policy}"')
def step_cookie_same_site(context, name, policy):
    cookie = _cookie(context, name)
    assert cookie is not None and cookie["sameSite"] == policy, f"cookie {name!r}: {cookie}"


@then('the provider should have received a "{grant}" token request')
def step_provider_token_request(context, grant):
    requests = browser_support.provider(context).requests_to("/oauth2/token")
    grants = [request.form.get("grant_type") for request in requests]
    assert grant in grants, f"token requests of the provider: {grants}"


@then("the provider should have received no token request")
def step_provider_no_token_request(context):
    requests = browser_support.provider(context).requests_to("/oauth2/token")
    assert not requests, f"unexpected token requests: {[r.form for r in requests]}"


@then("I should be asked to sign in at the provider")
def step_asked_to_sign_in(context):
    provider_url = context.e2e.servers["provider"].url
    expect(context.page).to_have_url(re.compile(f"^{re.escape(provider_url)}/oauth2/authorize"))
    expect(context.page.get_by_role("heading", name="Sign in")).to_be_visible()


@when('I sign in at the provider as the user "{email}" with the password "{password}"')
def step_sign_in_at_provider(context, email, password):
    log_in_at_provider(context, email, password)


@when("I sign in at the provider")
def step_sign_in_at_the_provider(context):
    log_in_at_provider(context, context.browser_user.email)


@given('a user holding the scopes "{scopes}" exists at the provider')
def step_user_exists(context, scopes):
    add_user(context, scopes.split())


@given("a user holding no scope exists at the provider")
def step_user_without_scope_exists(context):
    add_user(context, [])


@given('I remember the value of the cookie "{name}"')
def step_remember_cookie(context, name):
    cookie = _cookie(context, name)
    assert cookie is not None, f"no cookie {name!r}"
    context.remembered_cookies = {
        **getattr(context, "remembered_cookies", {}),
        name: cookie["value"],
    }


@then('the cookie "{name}" should differ from the remembered value')
def step_cookie_changed(context, name):
    cookie = _cookie(context, name)
    assert cookie is not None, f"no cookie {name!r}"
    assert cookie["value"] != context.remembered_cookies[name], f"cookie {name!r} did not change"


@given("the provider asks users for their consent")
def step_provider_consent(context):
    browser_support.provider(context).require_consent = True


@given("the provider revokes every token")
def step_provider_revokes(context):
    browser_support.provider(context).revoke_tokens()


@given("the provider ends every session")
def step_provider_ends_sessions(context):
    browser_support.provider(context).end_sessions()


@when('I return to the callback with the code "{code}" and the state of my login')
def step_callback_with_state(context, code):
    state = _cookie(context, "oauth_state")
    assert state is not None, "no login in progress: the oauth_state cookie is missing"
    context.page.goto(f"{context.base_url}/auth/callback?code={code}&state={state['value']}")


@when('I click "{target}" in the page content')
def step_click_in_content(context, target):
    """Click a link or a button of the page itself, not of the sidebar."""
    content = context.page.locator("main")
    for role in ("link", "button"):
        candidates = content.get_by_role(role, name=target, exact=True)
        if candidates.count():
            candidates.first.click()
            return
    raise AssertionError(f"the page content has no link or button called {target!r}")


@when("I dismiss the next confirmation")
def step_dismiss_next(context):
    context.dialogs.dismiss_next = True


@then('the page should have asked for a confirmation containing "{text}"')
def step_confirmation_asked(context, text):
    assert any(text in message for message in context.dialogs.messages), (
        f"confirmations asked: {context.dialogs.messages}"
    )


@then("the page should not have asked for any confirmation")
def step_no_confirmation(context):
    assert not context.dialogs.messages, f"confirmations asked: {context.dialogs.messages}"


@then('the field "{name}" should contain "{text}"')
def step_field_contains(context, name, text):
    from e2e_support.steps import field

    expect(field(context, name)).to_have_value(re.compile(re.escape(text)))


@when("I fill \"{name}\" with the text '{text}'")
def step_fill_with_text(context, name, text):
    """Fill a field with a text that contains double quotes (JSON, for instance)."""
    from e2e_support.steps import field

    field(context, name).fill(text)


@when('I fill "{name}" with the following lines')
def step_fill_with_lines(context, name):
    from e2e_support.steps import field

    field(context, name).fill(context.text)


@when('I clear "{name}"')
def step_clear(context, name):
    from e2e_support.steps import field

    field(context, name).fill("")
