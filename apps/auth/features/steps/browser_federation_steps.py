# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the browser scenarios of identity provider federation.

An external identity provider is played by the ``FakeOIDCProvider`` of e2e-support, served
on its own port: the application discovers it, sends the browser to its login page and
exchanges the code with it over HTTP, exactly as it does with a corporate provider.
"""

import secrets
import uuid
from urllib.parse import urlencode, urlsplit

from auth.core.encryption import encrypt_value
from auth.db.models.tenant import IdentityProvider, IdentityProviderType, Tenant
from auth.middlewares.tenant import TenantMiddleware
from behave import given, then, when
from e2e_support import behave_hooks as e2e
from e2e_support.oidc import Client, FakeOIDCProvider, User
from federation_steps import _provider
from sqlalchemy import select

IDP_SERVER = "identity provider"
TENANT_SERVER = "tenant application"


def _hostname(context):
    return urlsplit(context.base_url).hostname


@given("the tenants of the application are served by path")
def step_tenant_server(context):
    """A second server for the same application with the tenant middleware in front of it."""
    wrapped = TenantMiddleware(context.app, base_domain=_hostname(context))
    context.tenant_url = e2e.live_server(context, TENANT_SERVER, wrapped).url


@given('an external identity provider with the user "{email}" and the password "{password}"')
def step_external_provider(context, email, password):
    context.idp_client_id = f"client-{secrets.token_hex(4)}"
    context.idp_client_secret = secrets.token_urlsafe(16)
    context.idp_email = email
    context.idp_password = password
    context.idp = FakeOIDCProvider(
        users=[User(email=email, name="Bob Builder", password=password, id=str(uuid.uuid4()))],
        clients=[
            Client(
                context.idp_client_id,
                context.idp_client_secret,
                redirect_uris=(f"http://{_hostname(context)}:*/federation/callback",),
            )
        ],
    )
    # One server per scenario: the provider of a scenario must not answer the next one.
    name = f"{IDP_SERVER} {uuid.uuid4().hex[:8]}"
    server = e2e.live_server(context, name, context.idp)
    context.add_cleanup(lambda: (server.stop(), context.e2e.servers.pop(name, None)))
    context.idp_url = server.url


@given('the tenant "{slug}" trusts the external identity provider as "{name}"')
def step_trust_provider(context, slug, name):
    tenant = context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()
    context.database.sync_session.add(
        IdentityProvider(
            tenant_id=tenant.id,
            name=name,
            provider_type=IdentityProviderType.OIDC,
            discovery_url=f"{context.idp_url}/.well-known/openid-configuration",
            client_id=context.idp_client_id,
            client_secret_encrypted=encrypt_value(context.idp_client_secret),
            scopes=["openid", "profile", "email"],
            is_active=True,
            auto_provision=True,
            allow_linking=True,
        )
    )
    context.database.commit()


@given(
    'the visitor started the sign-in with "{name}" for the tenant "{slug}" returning to "{path}"'
)
@when('the visitor starts the sign-in with "{name}" for the tenant "{slug}" returning to "{path}"')
def step_start(context, name, slug, path):
    query = urlencode({"redirect_uri": path, "state": "orig-state"})
    idp_id = _provider(context, name).id
    context.page.goto(f"{context.tenant_url}/t/{slug}/federation/{idp_id}/authorize?{query}")


@given("the visitor signs in at the identity provider")
@when("the visitor signs in at the identity provider")
def step_sign_in_at_idp(context):
    context.page.get_by_label("Email").fill(context.idp_email)
    context.page.get_by_label("Password").fill(context.idp_password)
    context.page.get_by_role("button", name="Sign in").click()


@when('the visitor signs in at the identity provider with the password "{password}"')
def step_sign_in_at_idp_with(context, password):
    context.page.get_by_label("Email").fill(context.idp_email)
    context.page.get_by_label("Password").fill(password)
    context.page.get_by_role("button", name="Sign in").click()


@given("the identity provider forgot its sessions")
def step_forget_sessions(context):
    context.idp.end_sessions()


@then("the browser is at the identity provider")
def step_at_idp(context):
    context.page.wait_for_url(f"{context.idp_url}/**")


@then("the identity provider received the code, the client secret and a PKCE verifier")
def step_idp_token_request(context):
    request = context.idp.last_request("/oauth2/token")
    assert request.form["grant_type"] == "authorization_code"
    assert request.form["client_secret"] == context.idp_client_secret
    assert request.form["code"] and request.form["code_verifier"]
