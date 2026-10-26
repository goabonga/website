# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the identity provider federation feature."""

import asyncio
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
from auth.core.encryption import encrypt_value
from auth.db.models.tenant import (
    FederatedIdentity,
    IdentityProvider,
    IdentityProviderType,
    Tenant,
    TenantMember,
)
from auth.db.models.user import User, UserEmail
from auth.middlewares.tenant import TenantMiddleware
from auth.services import federation as federation_module
from auth.services.tenant_role import tenant_role_service
from behave import given, then, when
from helpers import fresh_encryption_key
from sqlalchemy import func, select

IDP = "https://idp.example.org"
CALLBACK = "http://acme.auth.example.test/federation/callback"


class FakeIdentityProvider:
    """An OpenID Connect provider answering through ``httpx.MockTransport``."""

    def __init__(self):
        self.email = "bob@example.com"
        self.token_requests = []

    def handler(self, request):
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": IDP,
                    "authorization_endpoint": f"{IDP}/authorize",
                    "token_endpoint": f"{IDP}/token",
                    "userinfo_endpoint": f"{IDP}/userinfo",
                    "jwks_uri": f"{IDP}/jwks",
                },
            )
        if path == "/token":
            self.token_requests.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"access_token": "idp-access", "token_type": "Bearer"})
        if path == "/userinfo":
            return httpx.Response(
                200,
                json={
                    "sub": f"idp|{self.email}",
                    "email": self.email,
                    "email_verified": True,
                    "name": "Bob Builder",
                    "given_name": "Bob",
                    "family_name": "Builder",
                },
            )
        return httpx.Response(404)


def _provider(context, name):
    return context.database.sync_session.scalars(
        select(IdentityProvider).where(IdentityProvider.name == name)
    ).one()


# ------------------------------------------------------------------ fixtures
@given("identity provider secrets are encrypted with a fresh key")
def step_provider_secret_key(context):
    context.encryption = fresh_encryption_key(context)
    patcher = patch("auth.core.encryption._encryption", None)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the tenant "{slug}" has its default roles')
def step_default_roles(context, slug):
    tenant = context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()
    asyncio.run(tenant_role_service.create_default_roles(context.db, tenant))
    context.database.commit()


@given('the tenant "{slug}" has an OpenID Connect provider "{name}"')
def step_provider(context, slug, name):
    tenant = context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()
    session = context.database.sync_session
    session.add(
        IdentityProvider(
            tenant_id=tenant.id,
            name=name,
            provider_type=IdentityProviderType.OIDC,
            discovery_url=f"{IDP}/.well-known/openid-configuration",
            client_id="acme-client",
            client_secret_encrypted=encrypt_value("idp-secret"),
            scopes=["openid", "profile", "email"],
            is_active=True,
            auto_provision=True,
            allow_linking=True,
        )
    )
    context.database.commit()
    context.idp = FakeIdentityProvider()
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(context.idp.handler), **kwargs)

    patcher = patch.object(federation_module.httpx, "AsyncClient", side_effect=client_factory)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given('the visitor browses the tenant "{slug}" at "{host}"')
def step_browse(context, slug, host):
    context.client.close()
    wrapped = TenantMiddleware(context.app, base_domain="auth.example.test")
    context.client = context.client_class(wrapped, base_url=f"http://{host}")


@given('the provider "{name}" does not provision accounts')
def step_no_provisioning(context, name):
    _provider(context, name).auto_provision = False
    context.database.commit()


@given('the provider "{name}" is switched off')
def step_switch_off(context, name):
    _provider(context, name).is_active = False
    context.database.commit()


# ---------------------------------------------------------------- the listing
@then('the providers include "{name}" with the button text "{text}"')
def step_providers_listed(context, name, text):
    providers = context.response.json()["providers"]
    assert any(p["name"] == name and p["button_text"] == text for p in providers), providers


# ------------------------------------------------------------------- sign in
def _start(context, idp_id, return_to):
    context.response = context.client.get(
        f"/federation/{idp_id}/authorize",
        params={"redirect_uri": return_to, "state": "orig-state"},
        follow_redirects=False,
    )
    if context.response.status_code == 302:
        context.authorization = urlparse(context.response.headers["location"])
        context.authorization_query = parse_qs(context.authorization.query)


@given('the visitor started the sign-in with "{name}" and returns to "{return_to}"')
@when('the visitor starts the sign-in with "{name}" and returns to "{return_to}"')
def step_start(context, name, return_to):
    _start(context, _provider(context, name).id, return_to)


@when('the visitor starts the sign-in with the unknown provider "{idp_id}"')
def step_start_unknown(context, idp_id):
    _start(context, idp_id, "/portal")


@then("the visitor is redirected to the identity provider authorization endpoint")
def step_redirected_to_idp(context):
    assert context.response.status_code == 302
    assert (
        f"{context.authorization.scheme}://{context.authorization.netloc}{context.authorization.path}"
        == f"{IDP}/authorize"
    )


@then(
    "the authorization request carries the client id, the callback URL, a state, a nonce and an S256 code challenge"
)
def step_authorization_request(context):
    query = context.authorization_query
    assert query["client_id"] == ["acme-client"]
    assert query["redirect_uri"] == [CALLBACK]
    assert query["response_type"] == ["code"]
    assert query["state"] and query["nonce"] and query["code_challenge"]
    assert query["code_challenge_method"] == ["S256"]


def _callback(context, email, code="abc"):
    context.idp.email = email
    context.idp.token_requests.clear()
    context.response = context.client.get(
        "/federation/callback",
        params={"code": code, "state": context.authorization_query["state"][0]},
        follow_redirects=False,
    )


@when('the identity provider sends the visitor back with the code "{code}" for "{email}"')
def step_callback(context, code, email):
    _callback(context, email, code)


@given('the visitor signed in with "{name}" as "{email}"')
@when('the visitor signs in with "{name}" as "{email}"')
def step_sign_in(context, name, email):
    _start(context, _provider(context, name).id, "/portal")
    _callback(context, email)


@when('the visitor signs in again with "{name}" as "{email}"')
def step_sign_in_again(context, name, email):
    context.client.cookies.clear()
    step_sign_in(context, name, email)


@when('the identity provider reports the error "{error}"')
def step_idp_error(context, error):
    context.response = context.client.get(
        "/federation/callback", params={"error": error}, follow_redirects=False
    )


@when('the visitor opens the callback "{query}"')
def step_open_callback(context, query):
    context.response = context.client.get(f"/federation/callback?{query}", follow_redirects=False)


# ----------------------------------------------------------------- assertions
@then('the visitor is redirected to "/portal?state=" followed by the original state')
def step_redirect_portal(context):
    assert context.response.status_code == 302, context.response.text
    assert context.response.headers["location"] == "/portal?state=orig-state"


@then('the visitor is redirected to a path starting with "{prefix}"')
def step_visitor_redirect_prefix(context, prefix):
    assert context.response.headers["location"].startswith(prefix), context.response.headers


@then('the response sets an HttpOnly session cookie named "{name}"')
def step_cookie_named(context, name):
    cookies = context.response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(f"{name}="))
    assert "HttpOnly" in session_cookie


def _user_by_email(context, email):
    return context.database.sync_session.scalars(
        select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).first()


@then('the user "{email}" exists with a verified address')
def step_user_verified(context, email):
    user = _user_by_email(context, email)
    assert user is not None and user.emails[0].is_verified


@then('the user "{email}" is a member of the tenant "{slug}"')
def step_user_member(context, email, slug):
    user = _user_by_email(context, email)
    member = context.database.sync_session.scalars(
        select(TenantMember)
        .join(Tenant)
        .where(Tenant.slug == slug, TenantMember.user_id == user.id)
    ).first()
    assert member is not None


@then('the identity provider received the code "{code}", the client secret and the PKCE verifier')
def step_token_request(context, code):
    form = context.idp.token_requests[0]
    assert form["code"] == [code]
    assert form["client_secret"] == ["idp-secret"]
    assert form["code_verifier"] and form["grant_type"] == ["authorization_code"]


@then('there is exactly {count:d} user with the address "{email}"')
def step_user_count(context, count, email):
    total = context.database.sync_session.scalar(
        select(func.count(UserEmail.id)).where(func.lower(UserEmail.email) == email.lower())
    )
    assert total == count


@then('there is no user with the address "{email}"')
def step_no_user(context, email):
    assert _user_by_email(context, email) is None


@then("the user has {count:d} federated identity")
def step_identity_count(context, count):
    total = context.database.sync_session.scalar(select(func.count(FederatedIdentity.id)))
    assert total == count
