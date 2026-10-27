# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of multi-factor authentication."""

import time

import pyotp
from behave import given, then, when
from browser_support import mail_code
from mfa_steps import _secret, _stored_mfa


def _displayed_secret(context):
    return context.page.locator("code.secret").inner_text().strip()


@given("I read the secret shown next to the QR code")
@when("I read the secret shown next to the QR code")
def step_read_secret(context):
    context.totp_secret = _displayed_secret(context)


@then("the QR code image of the page is displayed")
def step_qr_displayed(context):
    image = context.page.get_by_alt_text("TOTP QR Code")
    image.wait_for(state="visible")
    assert image.evaluate("img => img.complete && img.naturalWidth > 0"), "the QR code did not load"


@then("the secret shown next to the QR code is the one stored encrypted")
def step_secret_is_stored(context):
    assert _secret(context) == _displayed_secret(context)


@when("I enter the current code of the authenticator app in the setup form")
def step_enter_setup_code(context):
    context.page.get_by_label("Enter the 6-digit code").fill(pyotp.TOTP(context.totp_secret).now())


@then("TOTP is {state} for the user in the database")
def step_totp_state(context, state):
    assert _stored_mfa(context).totp_enabled is (state == "enabled")


@given("TOTP is enabled for the user of the browser")
def step_enable_for_user(context):
    context.execute_steps("Given TOTP is enabled for the user")


@when("I enter the e-mailed MFA code of {email}")
def step_enter_mail_code(context, email):
    context.page.get_by_label("Enter the 6-digit code").fill(mail_code(context, email))


@then("the page lists {count:d} backup codes")
def step_lists_codes(context, count):
    items = context.page.locator("#backup-codes li")
    items.first.wait_for(state="visible")
    context.backup_codes = [text.strip() for text in items.all_inner_texts()]
    assert len(context.backup_codes) == count, context.backup_codes


@given("the browser records the pages it visits")
def step_record_visits(context):
    """Remember every navigation, to check redirects that later features may continue."""
    context.visited = []

    def on_request(request):
        if request.is_navigation_request():
            context.visited.append(request.url)

    context.page.on("request", on_request)


@then('the browser visited "{fragment}"')
def step_visited(context, fragment):
    deadline = time.monotonic() + context.e2e.settings.timeout / 1000
    while time.monotonic() < deadline:
        if any(fragment in url for url in context.visited):
            return
        context.page.wait_for_timeout(50)
    raise AssertionError(f"{fragment!r} not among the visited pages: {context.visited}")
