# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the sessions and logout feature."""

import asyncio
from datetime import UTC, datetime, timedelta

from auth.db.models.user import Session, User, UserEmail
from auth.services.auth import AuthService
from auth.services.session import SessionService, hash_token
from behave import given, then, when
from factories import make_user
from sqlalchemy import func, select

SESSION_COOKIE = "session"


def _user(context, email):
    return context.database.sync_session.scalars(
        select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).one()


@given('a verified user "{email}" with the password "{password}"')
def step_verified_user(context, email, password):
    make_user(context.database.sync_session, email, password)
    context.database.commit()


@given('the user "{email}" is {state}')
def step_user_state(context, email, state):
    user = _user(context, email)
    if state == "inactive":
        user.is_active = False
    elif state == "unverified":
        user.emails[0].is_verified = False
    context.database.commit()


def _open_session(context, email):
    service = SessionService()
    token, csrf = asyncio.run(service.create_session(context.db, str(_user(context, email).id)))
    context.database.commit()
    context.session_service = service
    context.session_token, context.csrf_token = token, csrf
    context.session_row = context.database.sync_session.scalars(
        select(Session).where(Session.session_token_hash == hash_token(token))
    ).one()


@given('a session is opened for "{email}"')
@when('a session is opened for "{email}"')
def step_open_session(context, email):
    _open_session(context, email)


@given('a second session is opened for "{email}"')
def step_open_second_session(context, email):
    asyncio.run(SessionService().create_session(context.db, str(_user(context, email).id)))
    context.database.commit()


@when("the session expired one minute ago")
@given("the session expired one minute ago")
def step_session_expired(context):
    context.session_row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    context.database.commit()


@given("the session expires in {minutes:d} minutes")
def step_session_expires_soon(context, minutes):
    context.session_row.expires_at = datetime.now(UTC) + timedelta(minutes=minutes)
    context.database.commit()


def _resolves_to(context, token):
    user = asyncio.run(SessionService().get_user_by_session_token(context.db, token))
    return user


@then("the session token is not stored in clear")
def step_not_in_clear(context):
    assert context.session_row.session_token_hash != context.session_token
    assert context.session_row.session_token_hash == hash_token(context.session_token)


@then('the session token resolves to "{email}"')
def step_resolves(context, email):
    user = _resolves_to(context, context.session_token)
    assert user is not None and user.id == _user(context, email).id


@then("the session token resolves to nobody")
def step_resolves_nobody(context):
    assert _resolves_to(context, context.session_token) is None


@then("an unknown session token resolves to nobody")
def step_unknown_token(context):
    assert _resolves_to(context, "not-a-session-token") is None


@then("the session accepts its own CSRF token")
def step_csrf_ok(context):
    assert asyncio.run(
        context.session_service.verify_csrf_token(
            context.db, context.session_token, context.csrf_token
        )
    )


@then('the session rejects the CSRF token "{token}"')
def step_csrf_rejected(context, token):
    assert not asyncio.run(
        context.session_service.verify_csrf_token(context.db, context.session_token, token)
    )


# ------------------------------------------------------------------- HTTP
@when('I post to "{path}" with the session cookie')
def step_post_with_cookie(context, path):
    context.client.cookies.set(SESSION_COOKIE, context.session_token)
    context.response = context.client.post(path, follow_redirects=False)


@when('I request "{path}" with the session cookie')
def step_get_with_cookie(context, path):
    context.client.cookies.set(SESSION_COOKIE, context.session_token)
    context.response = context.client.get(path, follow_redirects=False)


@then("the response clears the session cookie")
def step_clears_cookie(context):
    header = context.response.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE}=" in header and "Max-Age=0" in header, header


@then("the response sets a refreshed session cookie")
def step_refreshed_cookie(context):
    header = context.response.headers.get("set-cookie", "")
    assert header.startswith(f"{SESSION_COOKIE}={context.session_token}"), header
    assert "HttpOnly" in header


@then("the session lasts for about {days:d} days")
def step_lasts_days(context, days):
    context.database.sync_session.refresh(context.session_row)
    remaining = context.session_row.expires_at - datetime.now(UTC)
    assert timedelta(days=days) - timedelta(minutes=5) < remaining <= timedelta(days=days)


@then("the response does not set a session cookie")
def step_no_cookie(context):
    assert "set-cookie" not in context.response.headers


@then('the user "{email}" has {count:d} active sessions')
def step_active_sessions(context, email, count):
    context.database.sync_session.expire_all()
    rows = context.database.sync_session.scalars(
        select(Session).where(
            Session.user_id == _user(context, email).id, Session.revoked_at.is_(None)
        )
    ).all()
    assert len(rows) == count


# ------------------------------------------------------------ authentication
@when('"{email}" authenticates with the password "{password}"')
def step_authenticate(context, email, password):
    context.authenticated = asyncio.run(AuthService().authenticate(context.db, email, password))


@then("the authentication succeeds")
def step_auth_succeeds(context):
    assert context.authenticated is not None


@then("the authentication fails")
def step_auth_fails(context):
    assert context.authenticated is None
