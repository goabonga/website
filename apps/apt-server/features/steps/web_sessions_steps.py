# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the web login sessions feature (identity provider faked in-process)."""

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
from apt_server.auth.introspection import introspection_client
from apt_server.config import settings
from apt_server.routes import auth as auth_routes
from apt_server.services import session
from behave import given, then, when

ISSUER = "https://issuer.example"
REAL_ASYNC_CLIENT = httpx.AsyncClient


def unsigned_jwt(claims):
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}."


@given('the identity provider is configured with web client "{client_id}"')
def configure_identity_provider(context, client_id):
    context.patch(settings, "oauth2_issuer", ISSUER)
    context.patch(settings, "oauth2_swagger_client_id", client_id)
    context.patch(settings, "session_secret", "behave-secret")
    context.patch(settings, "apt_gpg_key_id", "")
    context.idp = {"token_status": 200, "sub": "u-1", "email": "alice@example.com"}

    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            if context.idp["token_status"] != 200:
                return httpx.Response(context.idp["token_status"], json={"error": "invalid_grant"})
            token = unsigned_jwt({"sub": context.idp["sub"]})
            return httpx.Response(200, json={"access_token": token})
        if request.url.path.endswith("/userinfo"):
            return httpx.Response(200, json={"email": context.idp["email"], "nickname": "Alice"})
        return httpx.Response(404)

    context.patch(
        auth_routes.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )


@given('the identity provider knows user "{sub}" with email "{email}"')
def idp_user(context, sub, email):
    context.idp.update(sub=sub, email=email)


@given("the identity provider rejects the authorization code")
def idp_rejects(context):
    context.idp["token_status"] = 400


@when("I start the web login")
def start_login(context):
    context.response = context.client.get("/login", follow_redirects=False)
    context.login_state = None
    if context.response.status_code == 307:
        query = parse_qs(urlparse(context.response.headers["location"]).query)
        context.login_state = query["state"][0]
        context.state_cookie = context.response.cookies.get("oauth_state")


def callback(context, state, with_cookie=True):
    headers = {"Cookie": f"oauth_state={context.state_cookie}"} if with_cookie else {}
    context.response = context.client.get(
        "/callback", params={"code": "abc", "state": state}, headers=headers, follow_redirects=False
    )


@when("I return from the identity provider with a valid code")
def return_valid(context):
    callback(context, context.login_state)


@when("I return from the identity provider with a forged state")
def return_forged(context):
    callback(context, "forged-state")


@when("I return from the identity provider without the state cookie")
def return_without_cookie(context):
    context.state_cookie = ""
    callback(context, "whatever", with_cookie=False)


@then("the response redirects to the authorization endpoint with a PKCE challenge")
def redirects_to_authorize(context):
    location = urlparse(context.response.headers["location"])
    query = parse_qs(location.query)
    assert location.path == "/oauth2/authorize"
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"][0]
    assert query["client_id"] == ["web-client"]


@then("the OAuth state cookie is set")
def state_cookie_set(context):
    assert session.read_state_cookie(context.state_cookie) is not None


@then('the response redirects to "{path}"')
def redirects_to(context, path):
    assert context.response.headers["location"] == path


@then('a session cookie is set for "{email}"')
def session_cookie_set(context, email):
    data = session.read_session_cookie(context.response.cookies["apt_session"])
    assert data is not None and data.display_name == email


@then("the session cookie is cleared")
def session_cookie_cleared(context):
    assert "Max-Age=0" in context.response.headers["set-cookie"]


@given('the auth service accepts the session token "{token}" for user "{sub}"')
def accept_session_token(context, token, sub):
    async def validate(presented):
        assert presented == token
        return {"sub": sub, "scope": "apt:read"}

    context.patch(introspection_client, "validate_opaque_token", validate)


@given('I have a session for "{email}" with token "{token}"')
def have_session(context, email, token):
    context.session_cookie = session.create_session_cookie(token, display_name=email)


@when('I request "{path}" with my session')
def request_with_session(context, path):
    context.response = context.client.get(
        path, headers={"Cookie": f"apt_session={context.session_cookie}"}
    )


@when("I log out")
def log_out(context):
    context.response = context.client.get("/logout", follow_redirects=False)
