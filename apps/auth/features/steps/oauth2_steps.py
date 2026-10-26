# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the OAuth2 and OpenID Connect authorization server feature."""

import json
import secrets
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from behave import given, then, when
from oauth2_support import (
    REDIRECT_URI,
    authorize,
    client_of,
    create_client,
    token_request,
)


# ------------------------------------------------------------------- clients
@given('a confidential client "{name}" with the scopes "{scopes}" that skips consent')
def step_confidential_client(context, name, scopes):
    create_client(context, name, scopes, confidential=True, consent=False)


@given('a public client "{name}" with the scopes "{scopes}" that requires consent')
def step_public_client(context, name, scopes):
    create_client(context, name, scopes, confidential=False, consent=True)


@given('the scope group "{group}" covers the resources "{resources}"')
def step_scope_group(context, group, resources):
    from auth.config import settings

    groups = {group: [name.strip() for name in resources.split(",")]}
    patcher = patch.object(settings, "scope_groups", groups)
    patcher.start()
    context.add_cleanup(patcher.stop)


@then('a client allowed the scopes "{allowed}" may be granted "{scope}"')
def step_may_be_granted(context, allowed, scope):
    from auth.services.token_exchange import TokenExchangeService

    assert TokenExchangeService().scope_matches_allowed(scope, allowed.split())


@then('a client allowed the scopes "{allowed}" may not be granted "{scope}"')
def step_may_not_be_granted(context, allowed, scope):
    from auth.services.token_exchange import TokenExchangeService

    assert not TokenExchangeService().scope_matches_allowed(scope, allowed.split())


# ----------------------------------------------------------------- authorize
@given('the client asks for an authorization code with the scopes "{scopes}"')
@when('the client asks for an authorization code with the scopes "{scopes}"')
def step_authorize(context, scopes):
    authorize(
        context,
        client_id=client_of(context)["client_id"],
        redirect_uri=REDIRECT_URI,
        scopes=scopes,
    )


@when('the client "{name}" asks for an authorization code with the scopes "{scopes}"')
def step_authorize_named(context, name, scopes):
    context.current_client = name
    authorize(
        context, client_id=client_of(context)["client_id"], redirect_uri=REDIRECT_URI, scopes=scopes
    )


@when("the client asks for an authorization code without a code challenge")
def step_authorize_without_pkce(context):
    authorize(
        context,
        client_id=client_of(context)["client_id"],
        redirect_uri=REDIRECT_URI,
        scopes="openid",
        pkce=False,
    )


@when(
    'the client asks for an authorization code with the client id "{client_id}" and the redirect URI "{redirect_uri}"'
)
def step_authorize_custom(context, client_id, redirect_uri):
    real_id = context.clients[client_id]["client_id"] if client_id in context.clients else client_id
    authorize(context, client_id=real_id, redirect_uri=redirect_uri, scopes="openid")


@then('the browser is redirected to the client with a code and the state "{state}"')
def step_redirected_with_code(context, state):
    assert context.response.status_code == 302, context.response.text[:300]
    query = parse_qs(urlparse(context.response.headers["location"]).query)
    assert query["state"] == [state] and query["code"], query
    context.code = query["code"][0]


@then('the browser is redirected to the client with the error "{error}"')
def step_redirected_with_error(context, error):
    assert context.response.status_code == 302, context.response.text[:300]
    location = context.response.headers["location"]
    assert location.startswith(REDIRECT_URI), location
    assert parse_qs(urlparse(location).query)["error"] == [error], location


@then("the response is an HTML error page")
def step_html_error(context):
    assert "text/html" in context.response.headers["content-type"]


@when("the user approves the consent")
def step_approve(context):
    _consent(context, "allow")


@when("the user denies the consent")
def step_deny(context):
    _consent(context, "deny")


def _consent(context, decision):
    params = context.authorize_params
    context.response = context.client.post(
        "/oauth2/authorize",
        data={
            "consent": decision,
            "client_id": params["client_id"],
            "redirect_uri": params["redirect_uri"],
            "scope": params["scope"],
            "state": params["state"],
            "code_challenge": params["code_challenge"],
            "code_challenge_method": "S256",
            "nonce": params["nonce"],
        },
        follow_redirects=False,
    )


# --------------------------------------------------------------------- tokens
def _code_exchange(context, code, verifier):
    return token_request(
        context,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )


@given("the client exchanges the code with its credentials")
@when("the client exchanges the code with its credentials")
def step_exchange(context):
    _code_exchange(context, context.code, context.verifier)


@when("the client exchanges the same code again")
def step_exchange_again(context):
    _code_exchange(context, context.code, context.verifier)


@when("the client exchanges the code with a wrong verifier")
def step_exchange_wrong_verifier(context):
    _code_exchange(context, context.code, secrets.token_urlsafe(48))


@given('the client obtained tokens for the scopes "{scopes}"')
def step_obtained_tokens(context, scopes):
    authorize(
        context,
        client_id=client_of(context)["client_id"],
        redirect_uri=REDIRECT_URI,
        scopes=scopes,
    )
    _code_exchange(context, context.code, context.verifier)
    assert context.response.status_code == 200, context.response.text


@then("the token response contains an access token, a refresh token and an ID token")
def step_token_parts(context):
    assert all(context.tokens.get(k) for k in ("access_token", "refresh_token", "id_token"))


def _decode(context, token):
    jwks = context.client.get("/.well-known/jwks.json").json()["keys"]
    kid = jwt.get_unverified_header(token)["kid"]
    jwk = next(key for key in jwks if key["kid"] == kid)
    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})


@then("the access token is signed by a key published at the JWKS endpoint")
def step_signed_by_published_key(context):
    claims = _decode(context, context.tokens["access_token"])
    assert claims["sub"]


@then('the access token has the issuer "{issuer}" and the scope "{scope}"')
def step_access_token_claims(context, issuer, scope):
    claims = _decode(context, context.tokens["access_token"])
    assert claims["iss"] == issuer
    assert claims["scope"] == scope


@then('the ID token carries the nonce "{nonce}"')
def step_id_token_nonce(context, nonce):
    assert _decode(context, context.tokens["id_token"])["nonce"] == nonce


@then('the token error is "{error}"')
def step_token_error(context, error):
    body = context.response.json()
    detail = body.get("detail", body)
    assert detail["error"] == error, body


# -------------------------------------------------------------------- userinfo
@when("the client requests the userinfo with the access token")
def step_userinfo(context):
    context.response = context.client.get(
        "/userinfo", headers={"Authorization": f"Bearer {context.tokens['access_token']}"}
    )


@then("the userinfo has no name claim")
def step_no_name_claim(context):
    assert not context.response.json().get("name")


# ----------------------------------------------------------- client credentials
@when('the client requests a token with the client credentials grant for the scope "{scope}"')
def step_client_credentials(context, scope):
    token_request(context, {"grant_type": "client_credentials", "scope": scope})


@when('the client requests a token with the client credentials grant using the secret "{secret}"')
def step_client_credentials_secret(context, secret):
    client = client_of(context)
    form = {"grant_type": "client_credentials", "scope": "introspect"}
    if secret == "-":
        context.response = context.client.post(
            "/oauth2/token", data={**form, "client_id": client["client_id"]}
        )
    else:
        context.response = context.client.post(
            "/oauth2/token", data=form, auth=(client["client_id"], secret)
        )


@when("the client requests a token with the password grant")
def step_password_grant(context):
    token_request(
        context,
        {"grant_type": "password", "username": "alice@example.com", "password": "Sup3r!secret"},
    )


@then("the token response has no refresh token")
def step_no_refresh_token(context):
    assert not context.response.json().get("refresh_token")


# --------------------------------------------------------------------- refresh
@when("the client refreshes the tokens")
def step_refresh(context):
    context.previous_refresh = context.tokens["refresh_token"]
    token_request(
        context, {"grant_type": "refresh_token", "refresh_token": context.tokens["refresh_token"]}
    )


@when("the client refreshes the tokens with the previous refresh token")
def step_refresh_previous(context):
    token_request(
        context, {"grant_type": "refresh_token", "refresh_token": context.previous_refresh}
    )


@then("the response contains a new refresh token")
def step_new_refresh_token(context):
    assert context.tokens["refresh_token"] != context.previous_refresh


@when("the client revokes the current refresh token")
def step_revoke_refresh(context):
    _revoke(context, context.tokens["refresh_token"], "refresh_token")


@when("the client revokes the access token")
def step_revoke_access(context):
    _revoke(context, context.tokens["access_token"], "access_token")


def _revoke(context, token, hint):
    client = client_of(context)
    context.response = context.client.post(
        "/oauth2/revoke",
        data={"token": token, "token_type_hint": hint},
        auth=(client["client_id"], client["secret"]),
    )


# ------------------------------------------------------------------ introspection
@when("the client introspects the access token")
def step_introspect(context):
    client = client_of(context)
    context.response = context.client.post(
        "/oauth2/introspect",
        data={"token": context.tokens["access_token"]},
        auth=(client["client_id"], client["secret"]),
    )


@then('the introspection says the token is active for "{scope}"')
def step_introspection_active(context, scope):
    body = context.response.json()
    assert body["active"] is True and body["scope"] == scope, body


@then("the introspection says the token is not active")
def step_introspection_inactive(context):
    assert context.response.json()["active"] is False


# ------------------------------------------------------------------------ CORS
@when('a browser at "{origin}" sends a preflight request to "{path}"')
def step_preflight(context, origin, path):
    context.response = context.client.options(
        path,
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )


@then('the response allows the origin "{origin}"')
def step_allows_origin(context, origin):
    assert context.response.headers.get("access-control-allow-origin") == origin


@then("the response does not allow any origin")
def step_denies_origin(context):
    assert "access-control-allow-origin" not in context.response.headers
