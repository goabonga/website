# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the registration and email verification feature."""

import asyncio
import io
import re
import uuid
from pathlib import Path

from auth.config import settings
from auth.db.models.user import UserEmail, UserPassword, UserProfile
from auth.services.upload import UploadError, UploadService
from behave import given, then, when
from mailcapture import capture_mail
from sqlalchemy import func, select
from sqlite_db import use_database
from starlette.datastructures import Headers, UploadFile

PROFILE = {"nickname": "ally", "firstname": "Ally", "lastname": "Doe"}


@given("an empty user database")
def step_empty_database(context):
    use_database(context)


@given("outgoing e-mails are captured")
def step_capture_mail(context):
    capture_mail(context)


def _register(context, email, password):
    context.response = context.client.post(
        "/auth/register/api", json={"email": email, "password": password, "profile": PROFILE}
    )


def _email_row(context, email):
    return context.database.sync_session.scalars(
        select(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).first()


@when('I register "{email}" with the password "{password}" through the API')
def step_register_api(context, email, password):
    _register(context, email, password)


@given('the address "{email}" is registered')
def step_registered(context, email):
    _register(context, email, "Sup3r!secret")
    assert context.response.status_code == 200, context.response.text


@then('the account "{email}" exists and is not verified yet')
def step_account_unverified(context, email):
    row = _email_row(context, email)
    assert row is not None and row.is_verified is False


@then('the account "{email}" exists and is verified')
def step_account_verified(context, email):
    context.database.sync_session.expire_all()
    row = _email_row(context, email)
    assert row is not None and row.is_verified is True and row.verified_at is not None


@then('no account exists for "{email}"')
def step_no_account(context, email):
    assert _email_row(context, email) is None


@then('the stored password of "{email}" is an Argon2id hash')
def step_password_hash(context, email):
    row = _email_row(context, email)
    password = context.database.sync_session.scalars(
        select(UserPassword).where(UserPassword.user_id == row.user_id)
    ).one()
    assert password.password_hash.startswith("$argon2id$")
    assert password.is_current is True


@then('the profile of "{email}" has the nickname "{nickname}"')
def step_profile(context, email, nickname):
    row = _email_row(context, email)
    profile = context.database.sync_session.scalars(
        select(UserProfile).where(UserProfile.user_id == row.user_id)
    ).one()
    assert profile.nickname == nickname
    assert profile.name == "Ally Doe"


# ------------------------------------------------------------------ e-mails
@then('a verification e-mail with a 6 digit code was sent to "{email}"')
def step_code_sent(context, email):
    messages = context.mailbox.to(email)
    assert len(messages) == 1, context.mailbox.messages
    assert re.search(r"\b\d{6}\b", messages[0]["text"]), messages[0]["text"]


@then('{count:d} e-mails were sent to "{email}"')
def step_mail_count(context, count, email):
    assert len(context.mailbox.to(email)) == count


@then('no e-mail was sent to "{email}"')
def step_no_mail(context, email):
    assert context.mailbox.to(email) == []


@then('the verification e-mail to "{email}" is an HTML document')
def step_html_mail(context, email):
    html = context.mailbox.to(email)[0]["html"]
    assert re.search(r"<html", html, re.I), html[:200]
    assert context.mailbox.last_code_for(email) in html


@then('the verification e-mail to "{email}" has a plain text alternative')
def step_text_mail(context, email):
    text = context.mailbox.to(email)[0]["text"]
    assert text and "<" not in text
    assert context.mailbox.last_code_for(email) in text


# ------------------------------------------------------------- verification
@when('I verify "{email}" with the code received by e-mail')
@given('I verify "{email}" with the code received by e-mail')
def step_verify_with_code(context, email):
    code = context.mailbox.last_code_for(email)
    context.response = context.client.post(
        "/auth/verify-email/api", json={"email": email, "code": code}
    )


@when('I verify "{email}" with the code "{code}"')
def step_verify_with_explicit_code(context, email, code):
    context.response = context.client.post(
        "/auth/verify-email/api", json={"email": email, "code": code}
    )


@when('I ask for a new verification code for "{email}"')
def step_resend(context, email):
    context.response = context.client.post("/auth/resend-verification/api", json={"email": email})


# ---------------------------------------------------------------- HTML form
def _form(email, confirm):
    return {
        "email": email,
        "password": "Sup3r!secret",
        "password_confirm": confirm,
        "nickname": "carol",
        "firstname": "Carol",
        "lastname": "Doe",
    }


@when('I submit the registration form for "{email}"')
def step_submit_form(context, email):
    context.response = context.client.post(
        "/auth/register", data=_form(email, "Sup3r!secret"), follow_redirects=False
    )


@when('I submit the registration form for "{email}" with a different confirmation')
def step_submit_form_mismatch(context, email):
    context.response = context.client.post(
        "/auth/register", data=_form(email, "Other!secret1"), follow_redirects=False
    )


@then('the browser is redirected to a path starting with "{prefix}"')
def step_redirect_prefix(context, prefix):
    assert context.response.headers["location"].startswith(prefix)


# ------------------------------------------------------------------ avatars
def _upload(content_type, size):
    return UploadFile(
        file=io.BytesIO(b"x" * size),
        filename="avatar",
        headers=Headers({"content-type": content_type}),
    )


@when('an avatar of type "{content_type}" and {size:d} {unit} is uploaded')
def step_upload_avatar(context, content_type, size, unit):
    size_bytes = size * (1024 if unit == "KB" else 1024 * 1024)
    context.upload_error = None
    context.stored_avatar = None
    try:
        context.stored_avatar = asyncio.run(
            UploadService().save_avatar(_upload(content_type, size_bytes), user_id=uuid.uuid4())
        )
    except UploadError as exc:
        context.upload_error = str(exc)


@then('the avatar is stored under "{prefix}"')
def step_avatar_stored(context, prefix):
    assert context.stored_avatar.startswith(prefix), context.stored_avatar
    assert (Path(settings.upload_directory) / context.stored_avatar).is_file()


@then('the upload is refused with "{message}"')
def step_upload_refused(context, message):
    assert context.upload_error and message in context.upload_error, context.upload_error
