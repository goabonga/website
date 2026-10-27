# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of the OAuth2 and OpenID Connect server.

A second live server plays the client application: its callback page prints the query of
the redirect it receives, and the steps redeem the code the way its back end would.
"""

import asyncio
import html
import secrets
from urllib.parse import urlencode, urlsplit

from auth.services.oauth2_client import OAuth2ClientService
from behave import given, then, when
from e2e_support import behave_hooks as e2e
from oauth2_steps import _decode
from oauth2_support import AUTH_CODE_GRANTS, authorization_params, client_of, token_request
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route

CLIENT_APPLICATION = "client application"


def _client_application():
    """A callback page that lists the parameters of the redirect it receives."""

    async def callback(request):
        items = "".join(
            f'<li>{html.escape(name)}: <code id="{html.escape(name)}">{html.escape(value)}</code></li>'
            for name, value in request.query_params.items()
        )
        return HTMLResponse(
            "<!doctype html><html><head><title>Client callback</title></head>"
            f"<body><h1>Client application</h1><ul>{items}</ul></body></html>"
        )

    return Starlette(routes=[Route("/callback", callback)])


def _origin(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _redirect_uri(context):
    server = e2e.live_server(context, CLIENT_APPLICATION, _client_application())
    return f"{server.url}/callback"


def _register(context, name, scopes, *, confidential, consent):
    redirect_uri = _redirect_uri(context)
    client, secret = asyncio.run(
        OAuth2ClientService().create_client(
            context.db,
            name=name,
            redirect_uris=[redirect_uri],
            allowed_scopes=scopes.split(),
            allowed_grant_types=AUTH_CODE_GRANTS,
            is_confidential=confidential,
            require_pkce=True,
            require_consent=consent,
            allowed_origins=[_origin(redirect_uri)],
        )
    )
    context.clients = getattr(context, "clients", {})
    context.clients[name] = {"client_id": client.client_id, "secret": secret}
    context.current_client = name
    context.redirect_uri = redirect_uri


@given('a client application "{name}" with the scopes "{scopes}" that skips consent')
def step_confidential(context, name, scopes):
    _register(context, name, scopes, confidential=True, consent=False)


@given('a client application "{name}" with the scopes "{scopes}" that requires consent')
def step_public(context, name, scopes):
    _register(context, name, scopes, confidential=False, consent=True)


def _open(context, client_id, scopes, redirect_uri=None, pkce=True):
    params = authorization_params(
        context,
        client_id=client_id,
        redirect_uri=redirect_uri or context.redirect_uri,
        scopes=scopes,
        pkce=pkce,
    )
    context.authorize_params = params
    context.page.goto(f"{context.base_url}/oauth2/authorize?{urlencode(params)}")


@given('the browser opens the authorization request of "{name}" for the scopes "{scopes}"')
@when('the browser opens the authorization request of "{name}" for the scopes "{scopes}"')
def step_open(context, name, scopes):
    context.current_client = name
    _open(context, client_of(context)["client_id"], scopes)


@when('the browser opens the authorization request of "{name}" without a code challenge')
def step_open_without_pkce(context, name):
    context.current_client = name
    _open(context, client_of(context)["client_id"], "openid", pkce=False)


@when(
    'the browser opens the authorization request with the client id "{client_id}" and the redirect URI "{redirect_uri}"'
)
def step_open_custom(context, client_id, redirect_uri):
    real_id = context.clients[client_id]["client_id"] if client_id in context.clients else client_id
    _open(context, real_id, "openid", redirect_uri)


@then("the callback page of the client application received a code and the state sent")
def step_callback_code(context):
    context.page.locator("#code").wait_for(state="visible")
    context.code = context.page.locator("#code").inner_text()
    assert context.code
    assert context.page.locator("#state").inner_text() == context.authorize_params["state"]


@then('the callback page of the client application received the error "{error}"')
def step_callback_error(context, error):
    context.page.locator("#error").wait_for(state="visible")
    assert context.page.locator("#error").inner_text() == error
    assert context.page.locator("#state").inner_text() == context.authorize_params["state"]


def _redeem(context, code, verifier):
    return token_request(
        context,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": context.redirect_uri,
            "code_verifier": verifier,
        },
    )


@given("the client application redeems the code of the callback page")
@when("the client application redeems the code of the callback page")
def step_redeem(context):
    _redeem(context, context.code, context.verifier)


@when("the client application redeems the same code again")
def step_redeem_again(context):
    _redeem(context, context.code, context.verifier)


@when("the client application redeems the code with a wrong verifier")
def step_redeem_wrong_verifier(context):
    _redeem(context, context.code, secrets.token_urlsafe(48))


@then('the access token has the issuer of the application and the scope "{scope}"')
def step_access_token_claims(context, scope):
    claims = _decode(context, context.tokens["access_token"])
    assert claims["iss"] == context.base_url
    assert claims["scope"] == scope


@then("the browser stayed on the authorization server")
def step_stayed_on_server(context):
    assert context.page.url.startswith(context.base_url), context.page.url


def _cross_origin_fetch(context, page_url, path, method="GET", data=None):
    """Call the authorization server from a page of another origin, as a browser application."""
    context.page.goto(page_url)
    context.fetch_result = context.page.evaluate(
        """async ([url, method, data]) => {
            try {
                const options = {method};
                if (data) {
                    options.body = new URLSearchParams(data);
                }
                const response = await fetch(url, options);
                return {ok: true, status: response.status, body: await response.text()};
            } catch (error) {
                return {ok: false, error: String(error)};
            }
        }""",
        [f"{context.base_url}{path}", method, data],
    )


@when('the page of the client application "{name}" calls "{path}" of the authorization server')
def step_registered_origin_calls(context, name, path):
    context.current_client = name
    _cross_origin_fetch(context, context.redirect_uri, path)


@when('a page of an unregistered application calls "{path}" of the authorization server')
def step_unregistered_origin_calls(context, path):
    server = e2e.live_server(context, "unregistered application", _client_application())
    _cross_origin_fetch(context, f"{server.url}/callback", path)


@when(
    'the page of the client application "{name}" posts to the token endpoint for the client credentials'
)
def step_registered_origin_posts_token(context, name):
    context.current_client = name
    client = client_of(context)
    _cross_origin_fetch(
        context,
        context.redirect_uri,
        "/oauth2/token",
        method="POST",
        data={
            "grant_type": "authorization_code",
            "code": "unknown",
            "client_id": client["client_id"],
        },
    )


@then("the browser let the page read the answer")
def step_cors_allowed(context):
    assert context.fetch_result["ok"], context.fetch_result


@then("the browser blocked the call to the authorization server")
def step_cors_blocked(context):
    assert not context.fetch_result["ok"], context.fetch_result
    assert "Failed to fetch" in context.fetch_result["error"], context.fetch_result
