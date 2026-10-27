# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of login and password reset."""

from urllib.parse import urlsplit

import pyotp
from auth.config import settings
from auth.db.models.user import Session
from auth.services.session import hash_token
from behave import given, then, when
from browser_sessions_steps import cookie
from browser_support import mail_code, mail_link
from login_steps import _user
from sessions_steps import _open_session
from sqlalchemy import select


@when('I sign in as "{email}" with the password "{password}"')
@given('I sign in as "{email}" with the password "{password}"')
def step_sign_in(context, email, password):
    context.page.get_by_label("Email").fill(email)
    context.page.get_by_label("Password").fill(password)
    context.page.get_by_role("button", name="Login", exact=True).click()


@given('I am on the login page asking to continue to "{target}"')
def step_login_with_next(context, target):
    context.page.goto(f"{context.base_url}/auth/login?next={target}")


@when("I enter the current code of the authenticator app")
def step_enter_totp(context):
    context.page.get_by_label("Authenticator code").fill(pyotp.TOTP(context.totp_secret).now())
    context.page.get_by_role("button", name="Login", exact=True).click()


@when("I enter the first backup code")
def step_enter_backup_code(context):
    context.page.get_by_label("Authenticator code").fill(context.backup_codes[0])
    context.page.get_by_role("button", name="Login", exact=True).click()


@when("I enter the code received by e-mail by {email}")
def step_enter_mail_code(context, email):
    context.page.get_by_label("Authenticator code").fill(mail_code(context, email))
    context.page.get_by_role("button", name="Login", exact=True).click()


@when('I enter the authenticator code "{code}"')
def step_enter_code(context, code):
    context.page.get_by_label("Authenticator code").fill(code)
    context.page.get_by_role("button", name="Login", exact=True).click()


@then('the session cookie of the browser belongs to "{email}"')
def step_cookie_owner(context, email):
    found = cookie(context, settings.session_cookie_name)
    assert found is not None, "the browser holds no session cookie"
    row = context.database.sync_session.scalars(
        select(Session).where(Session.session_token_hash == hash_token(found["value"]))
    ).one()
    assert row.user_id == _user(context, email).id


@then("the browser holds no session cookie")
def step_no_session_cookie(context):
    assert cookie(context, settings.session_cookie_name) is None


@then("the CSRF cookie of the browser can be read by the scripts of the page")
def step_csrf_readable(context):
    from auth.middlewares.tenant import get_csrf_cookie_name

    name = get_csrf_cookie_name()
    assert context.page.evaluate("document.cookie").count(f"{name}=") == 1


@then("the browser stays on the server of the application")
def step_stays_on_server(context):
    """The sign-in left the login page and the browser did not leave the application."""
    context.page.wait_for_url(lambda url: "/auth/login" not in url)
    assert urlsplit(context.page.url).netloc == urlsplit(context.base_url).netloc, context.page.url


@when('I open the password reset link e-mailed to "{email}"')
@given('I open the password reset link e-mailed to "{email}"')
def step_open_reset_link(context, email):
    context.page.goto(mail_link(context, email, "/auth/reset-password"))


@given('the browser holds the cookie of the session of "{email}"')
def step_hold_session_of(context, email):
    _open_session(context, email)
    context.execute_steps("Given the browser holds the cookie of the session")
