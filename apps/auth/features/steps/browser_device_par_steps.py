# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of the device flow and pushed requests."""

from urllib.parse import urlencode

import httpx
from behave import given, then, when
from oauth2_support import authorization_params, client_of

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


@given('the device requested a device code from the application for the scopes "{scopes}"')
@when('the device requests a device code from the application for the scopes "{scopes}"')
def step_request_device_code(context, scopes):
    """The device talks to the application over the network, like the browser."""
    context.current_client = "tv"
    context.response = httpx.post(
        f"{context.base_url}/oauth2/device",
        data={"client_id": client_of(context)["client_id"], "scope": scopes},
    )
    assert context.response.status_code == 200, context.response.text
    context.device = context.response.json()


@when("the device polls the application")
def step_poll(context):
    context.response = httpx.post(
        f"{context.base_url}/oauth2/token",
        data={
            "grant_type": DEVICE_GRANT,
            "device_code": context.device["device_code"],
            "client_id": client_of(context)["client_id"],
        },
    )


@given("the user scans the verification link of the device")
@when("the user scans the verification link of the device")
def step_open_verification_link(context):
    """Open ``verification_uri_complete`` the way a QR code would."""
    context.page.goto(context.device["verification_uri_complete"])


@when("the user opens the verification address of the device")
def step_open_verification_address(context):
    context.page.goto(context.device["verification_uri"])


@when("the user types the code of the device")
def step_type_code(context):
    context.page.get_by_label("Device Code").fill(context.device["user_code"])


@then("the verification address is served by the application")
def step_verification_address(context):
    assert context.device["verification_uri"].startswith(context.base_url), context.device


@then("the code of the device is displayed on the consent page")
def step_code_displayed(context):
    assert context.page.locator(".code-display .code").inner_text() == context.device["user_code"]


@then('the field "{name}" shows the code of the device')
def step_field_shows_code(context, name):
    assert context.page.get_by_label(name).input_value() == context.device["user_code"]


@when('the client application "{name}" pushes an authorization request for the scopes "{scopes}"')
def step_push(context, name, scopes):
    context.current_client = name
    client = client_of(context)
    form = authorization_params(
        context, client_id=client["client_id"], redirect_uri=context.redirect_uri, scopes=scopes
    )
    form.pop("client_id")
    context.authorize_params = {**form, "client_id": client["client_id"]}
    context.response = context.client.post(
        "/oauth2/par", data=form, auth=(client["client_id"], client["secret"])
    )
    assert context.response.status_code == 200, context.response.text
    context.request_uri = context.response.json()["request_uri"]


@given("the browser opens the pushed request URI")
@when("the browser opens the pushed request URI")
def step_follow_request_uri(context):
    query = urlencode(
        {"client_id": client_of(context)["client_id"], "request_uri": context.request_uri}
    )
    context.page.goto(f"{context.base_url}/oauth2/authorize?{query}")
