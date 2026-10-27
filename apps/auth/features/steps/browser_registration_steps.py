# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of registration."""

from auth.db.models.user import UserProfile
from behave import given, then, when
from browser_support import mail_code, mail_link
from registration_steps import _email_row
from sqlalchemy import select


@given('I fill the registration form for "{email}" with the password "{password}"')
@when('I fill the registration form for "{email}" with the password "{password}"')
def step_fill_registration(context, email, password):
    for label, value in (
        ("Nickname", "ally"),
        ("First Name", "Ally"),
        ("Last Name", "Doe"),
        ("Email", email),
        ("Password", password),
        ("Confirm Password", password),
    ):
        context.page.get_by_label(label).first.fill(value)


@when('I enter the e-mailed code of "{email}"')
def step_enter_code(context, email):
    context.page.get_by_label("Verification Code").fill(mail_code(context, email))


@when('I open the verification link e-mailed to "{email}"')
def step_open_link(context, email):
    context.page.goto(mail_link(context, email, "/auth/verify-email"))


@then('the password requirement "{text}" is {state}')
def step_requirement(context, text, state):
    item = context.page.locator("#password-requirements li", has_text=text)
    expected = "valid" if state == "met" else "invalid"
    assert item.get_attribute("class") == expected, item.get_attribute("class")


@then('the address "{email}" is {state} in the database')
def step_address_state(context, email, state):
    context.database.sync_session.expire_all()
    row = _email_row(context, email)
    assert row is not None and row.is_verified is (state == "verified")


@when('I choose the avatar file "{name}"')
def step_choose_avatar(context, name):
    # A 1x1 PNG, the smallest image the upload service accepts.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
    )
    context.page.locator("details", has_text="Profile Picture").locator("summary").click()
    context.page.get_by_label("Upload a photo").set_input_files(
        files=[{"name": name, "mimeType": "image/png", "buffer": png}]
    )


@then('the profile picture of "{email}" is stored under the uploads')
def step_picture_stored(context, email):
    # The application commits after it has answered: the browser can be ahead of the
    # database, so the profile is read again (in a new transaction) until it appears.
    profile = None
    for _ in range(50):
        context.database.sync_session.rollback()
        row = _email_row(context, email)
        profile = context.database.sync_session.scalars(
            select(UserProfile).where(UserProfile.user_id == row.user_id)
        ).one_or_none()
        if profile is not None and profile.picture_url:
            break
        context.page.wait_for_timeout(100)
    assert profile is not None, "no profile was stored"
    assert profile.picture_url and "/uploads/avatars/" in profile.picture_url, profile.picture_url
