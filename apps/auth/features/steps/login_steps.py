# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the login and password reset feature."""

import asyncio
import re
from urllib.parse import parse_qs, urlparse

import pyotp
from auth.api.deps import get_mfa_service
from auth.db.models.user import Session, User, UserEmail
from auth.services.session import hash_token
from behave import given, then, when
from helpers import patch_setting
from sqlalchemy import func, select

SESSION_COOKIE = "session"


def _user(context, email):
    return context.database.sync_session.scalars(
        select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).one()


@given("the test client talks plain HTTP")
def step_plain_http(context):
    """The session and challenge cookies are ``Secure``; the test client uses ``http://``."""
    patch_setting(context, "session_cookie_secure", False)


# --------------------------------------------------------------------- sign in
def _api_login(context, email, password, otp=None):
    payload = {"email": email, "password": password}
    if otp is not None:
        payload["otp"] = otp
    context.client.cookies.clear()
    context.response = context.client.post("/auth/login/api", json=payload)


@given('I signed in through the API as "{email}" with the password "{password}"')
@when('I sign in through the API as "{email}" with the password "{password}"')
def step_api_login(context, email, password):
    _api_login(context, email, password)


@when(
    'I sign in through the API as "{email}" using the password "{password}" and the code "{code}"'
)
def step_api_login_code(context, email, password, code):
    _api_login(context, email, password, code)


@when(
    'I sign in through the API as "{email}" using the password "{password}" and a valid TOTP code'
)
def step_api_login_totp(context, email, password):
    _api_login(context, email, password, pyotp.TOTP(context.totp_secret).now())


@then("the response sets an HttpOnly session cookie")
def step_session_cookie_set(context):
    header = context.response.headers.get("set-cookie", "")
    assert header.startswith(f"{SESSION_COOKIE}="), header
    assert "HttpOnly" in header
    context.session_token = re.match(rf"{SESSION_COOKIE}=([^;]+)", header).group(1)


@then("the response sets no session cookie")
def step_no_session_cookie(context):
    assert f"{SESSION_COOKIE}=" not in context.response.headers.get("set-cookie", "")


@then('the session cookie belongs to "{email}"')
def step_cookie_owner(context, email):
    row = context.database.sync_session.scalars(
        select(Session).where(Session.session_token_hash == hash_token(context.session_token))
    ).one()
    assert row.user_id == _user(context, email).id


# ------------------------------------------------------------------- the form
@when('I submit the login form for "{email}" with the password "{password}"')
def step_submit_login_form(context, email, password):
    _submit_login_form(context, email, password, "")


@when(
    'I submit the login form redirecting to "{next_url}" for "{email}" with the password "{password}"'
)
def step_submit_login_form_with_next(context, next_url, email, password):
    _submit_login_form(context, email, password, next_url)


def _submit_login_form(context, email, password, next_url):
    context.client.cookies.clear()
    context.response = context.client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": next_url},
        follow_redirects=False,
    )


@when("I submit the code of the authenticator app")
def step_submit_otp(context):
    context.response = context.client.post(
        "/auth/login",
        data={"otp": pyotp.TOTP(context.totp_secret).now(), "next": "/auth/mfa/status"},
        follow_redirects=False,
    )


# ------------------------------------------------------------------------ MFA
@given('the user "{email}" enabled TOTP')
def step_enable_totp(context, email):
    service = get_mfa_service()
    user_id = str(_user(context, email).id)

    async def enable():
        secret, _uri, _qr = await service.setup_totp(context.db, user_id, email)
        codes = await service.enable_totp(context.db, user_id, pyotp.TOTP(secret).now())
        await context.db.commit()
        return secret, codes

    context.totp_secret, context.backup_codes = asyncio.run(enable())
    context.database.sync_session.expire_all()


# -------------------------------------------------------------- password reset
@when('I ask for a password reset for "{email}"')
def step_forgot_password(context, email):
    patch_setting(context, "issuer", "https://auth.example.com")
    context.response = context.client.post("/auth/forgot-password/api", json={"email": email})


@then('a password reset e-mail was sent to "{email}"')
def step_reset_mail_sent(context, email):
    assert len(context.mailbox.to(email)) == 1


def _reset_token(context, email="alice@example.com"):
    message = context.mailbox.to(email)[-1]
    link = re.search(
        r"https://auth\.example\.com/auth/reset-password\?token=[^\s\"'<]+", message["text"]
    )
    return parse_qs(urlparse(link.group(0)).query)["token"][0]


@when('I choose the new password "{password}" with the e-mailed token')
def step_reset_password(context, password):
    context.response = context.client.post(
        "/auth/reset-password/api", json={"token": _reset_token(context), "password": password}
    )


@then('"{email}" can sign in with "{password}"')
def step_can_sign_in(context, email, password):
    _api_login(context, email, password)
    assert context.response.status_code == 200, context.response.text


@then('"{email}" can no longer sign in with "{password}"')
def step_cannot_sign_in(context, email, password):
    _api_login(context, email, password)
    assert context.response.status_code == 401
