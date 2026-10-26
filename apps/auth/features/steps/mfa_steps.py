# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the multi-factor authentication feature."""

import pyotp
from auth.db.models.user import UserMFA
from behave import given, then, when
from helpers import fresh_encryption_key
from sqlalchemy import select

SESSION_COOKIE = "session"


@given("an encryption key is configured")
def step_encryption_key(context):
    context.encryption = fresh_encryption_key(context)


def _post(context, path, payload=None):
    context.client.cookies.set(SESSION_COOKIE, context.session_token)
    context.response = context.client.post(path, json=payload)
    return context.response


def _stored_mfa(context):
    context.database.sync_session.expire_all()
    return context.database.sync_session.scalars(select(UserMFA)).first()


def _secret(context):
    return context.encryption.decrypt(_stored_mfa(context).totp_secret_encrypted).decode()


def _valid_code(context):
    return pyotp.TOTP(context.totp_secret).now()


# ------------------------------------------------------------------ enrolment
@given("I started the TOTP enrolment")
@when("I start the TOTP enrolment")
def step_start_enrolment(context):
    _post(context, "/auth/mfa/totp/setup")
    if context.response.status_code == 200:
        context.totp_secret = context.response.json()["secret"]


@then("the response provides a secret and a QR code image")
def step_secret_and_qr(context):
    body = context.response.json()
    assert len(body["secret"]) >= 16
    assert body["qr_code"], "missing QR code"


@then("the TOTP secret is stored encrypted")
def step_secret_encrypted(context):
    stored = _stored_mfa(context).totp_secret_encrypted
    assert context.totp_secret.encode() not in stored
    assert _secret(context) == context.totp_secret


@when("I confirm the enrolment with a valid code")
def step_confirm_valid(context):
    _post(context, "/auth/mfa/totp/verify", {"code": _valid_code(context)})
    if context.response.status_code == 200:
        context.backup_codes = context.response.json()["backup_codes"]


@when('I confirm the enrolment with the code "{code}"')
def step_confirm_code(context, code):
    _post(context, "/auth/mfa/totp/verify", {"code": code})


@given("TOTP is enabled for the user")
def step_totp_enabled(context):
    step_start_enrolment(context)
    step_confirm_valid(context)
    assert context.response.status_code == 200, context.response.text


@then("{count:d} backup codes are returned")
def step_backup_codes_returned(context, count):
    codes = context.response.json()["backup_codes"]
    assert len(codes) == count
    context.backup_codes = codes


@then("the MFA status shows TOTP enabled with {count:d} backup codes remaining")
def step_status_enabled(context, count):
    context.client.cookies.set(SESSION_COOKIE, context.session_token)
    body = context.client.get("/auth/mfa/status").json()
    assert body["totp_enabled"] is True
    assert body["backup_codes_remaining"] == count, body


@then("the MFA status shows TOTP disabled")
def step_status_disabled(context):
    context.client.cookies.set(SESSION_COOKIE, context.session_token)
    assert context.client.get("/auth/mfa/status").json()["totp_enabled"] is False


# ------------------------------------------------------------------ challenges
@when("I answer the challenge with a valid TOTP code")
def step_challenge_totp(context):
    _post(context, "/auth/mfa/verify", {"code": _valid_code(context)})


@when('I answer the challenge with the code "{code}"')
def step_challenge_code(context, code):
    _post(context, "/auth/mfa/verify", {"code": code})


@when("I answer the challenge with the first backup code")
def step_challenge_backup(context):
    _post(context, "/auth/mfa/verify", {"code": context.backup_codes[0]})


@when("I regenerate the backup codes")
def step_regenerate(context):
    context.previous_codes = list(context.backup_codes)
    _post(context, "/auth/mfa/backup-codes/regenerate", {"code": _valid_code(context)})


@then("the previous backup codes no longer work")
def step_previous_codes_dead(context):
    _post(context, "/auth/mfa/verify", {"code": context.previous_codes[0]})
    assert context.response.status_code == 400


@when('I disable TOTP with the code "{code}"')
def step_disable_code(context, code):
    _post(context, "/auth/mfa/totp/disable", {"code": code})


@when("I disable TOTP with a valid code")
def step_disable_valid(context):
    _post(context, "/auth/mfa/totp/disable", {"code": _valid_code(context)})


# ------------------------------------------------------------------ e-mail codes
@when("I ask for an MFA code by e-mail")
def step_email_code(context):
    _post(context, "/auth/mfa/email/send")


@then('an MFA e-mail with a 6 digit code was sent to "{email}"')
def step_mfa_mail_sent(context, email):
    assert len(context.mailbox.to(email)) == 1
    assert context.mailbox.last_code_for(email)


@when("I submit the e-mailed MFA code")
def step_submit_email_code(context):
    code = context.mailbox.last_code_for("alice@example.com")
    _post(context, "/auth/mfa/email/verify", {"code": code})
