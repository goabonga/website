# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the device authorization and pushed authorization request feature."""

from datetime import UTC, datetime, timedelta

from auth.db.models.oauth2 import DeviceCode
from behave import given, then, when
from helpers import patch_setting
from oauth2_support import (
    REDIRECT_URI,
    authorization_params,
    client_of,
    create_client,
    remember_code,
    token_request,
)
from sqlalchemy import select

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


@given('a public client "{name}" for the device flow with the scopes "{scopes}"')
def step_device_client(context, name, scopes):
    create_client(
        context, name, scopes, confidential=False, consent=True, grants=[DEVICE_GRANT], pkce=False
    )


@given("the device polling interval is {seconds:d} seconds")
def step_polling_interval(context, seconds):
    patch_setting(context, "device_code_interval", seconds)


# ---------------------------------------------------------------- device flow
@given('the device requested a device code for the scopes "{scopes}"')
@when('the device requests a device code for the scopes "{scopes}"')
def step_request_device_code(context, scopes):
    context.current_client = "tv"
    context.response = context.client.post(
        "/oauth2/device", data={"client_id": client_of(context)["client_id"], "scope": scopes}
    )
    if context.response.status_code == 200:
        context.device = context.response.json()


@when('the confidential client "{name}" requests a device code')
def step_other_client_device_code(context, name):
    client = client_of(context, name)
    context.response = context.client.post(
        "/oauth2/device",
        data={"client_id": client["client_id"]},
        auth=(client["client_id"], client["secret"]),
    )


@then("the device authorization contains a device code, a user code and a verification URI")
def step_device_authorization(context):
    body = context.response.json()
    assert body["device_code"] and body["user_code"]
    assert body["verification_uri"].endswith("/oauth2/device/verify")
    assert body["user_code"] in body["verification_uri_complete"]
    assert body["expires_in"] > 0 and body["interval"] >= 0


@when("the device polls the token endpoint")
def step_poll(context):
    context.current_client = "tv"
    token_request(
        context, {"grant_type": DEVICE_GRANT, "device_code": context.device["device_code"]}
    )


@then("the token response contains an access token")
def step_device_tokens(context):
    body = context.response.json()
    assert body["access_token"]


@given("the device polled a moment ago")
def step_polled_recently(context):
    row = context.database.sync_session.scalars(select(DeviceCode)).one()
    row.last_poll_at = datetime.now(UTC)
    context.database.commit()


@given("the device code expired")
def step_device_code_expired(context):
    session = context.database.sync_session
    row = session.scalars(select(DeviceCode)).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    context.database.commit()


# ------------------------------------------------------------------ user steps
@when("the user opens the verification page for the user code")
def step_open_verification(context):
    context.response = context.client.get(
        "/oauth2/device/verify",
        params={"user_code": context.device["user_code"]},
        follow_redirects=False,
    )


@when("the user submits the user code")
def step_submit_user_code(context):
    _verify(context, context.device["user_code"])


@when('the user submits the user code "{user_code}"')
def step_submit_explicit_user_code(context, user_code):
    _verify(context, user_code)


def _verify(context, user_code):
    context.response = context.client.post(
        "/oauth2/device/verify", data={"user_code": user_code}, follow_redirects=False
    )


@when("the user approves the device")
def step_approve_device(context):
    _complete(context, "allow")


@when("the user denies the device")
def step_deny_device(context):
    _complete(context, "deny")


def _complete(context, decision):
    context.response = context.client.post(
        "/oauth2/device/complete",
        data={"user_code": context.device["user_code"], "consent": decision},
    )


# ----------------------------------------------------- pushed authorization requests
def _push(context, name, scopes, secret=None):
    context.current_client = name
    client = client_of(context)
    form = authorization_params(
        context, client_id=client["client_id"], redirect_uri=REDIRECT_URI, scopes=scopes
    )
    form.pop("client_id")
    context.response = context.client.post(
        "/oauth2/par",
        data=form,
        auth=(client["client_id"], secret or client["secret"]),
    )
    if context.response.status_code == 200:
        context.request_uri = context.response.json()["request_uri"]


@when('the client "{name}" pushes an authorization request for the scopes "{scopes}"')
def step_push(context, name, scopes):
    _push(context, name, scopes)


@when('the client "{name}" pushes an authorization request with the wrong secret')
def step_push_wrong_secret(context, name):
    _push(context, name, "openid", secret="wrong")


@then("the response carries a request URI")
def step_request_uri(context):
    assert context.request_uri.startswith("urn:ietf:params:oauth:request_uri:")


@when("the browser follows the request URI")
def step_follow_request_uri(context):
    context.response = context.client.get(
        "/oauth2/authorize",
        params={"client_id": client_of(context)["client_id"], "request_uri": context.request_uri},
        follow_redirects=False,
    )
    remember_code(context)
