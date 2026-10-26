# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the web authentication feature.

The authentication service (registration, verification, ROPC login, profile
and MFA) is replaced by an in-memory fake injected as a dependency. The OAuth2
token and userinfo endpoints used by the PKCE callback are served by an httpx
mock transport. Templates and routes are the real ones.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import httpx
import jwt
from behave import given, then, when
from fakes import FakeSession, Store

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.config import get_settings
from knowledge.database import get_db
from knowledge.models import Organization, OrganizationMember
from knowledge.models.enums import OrganizationMemberRole, PlanType
from knowledge.services.auth_api import (
    AuthAPIError,
    ProfileResult,
    RegisterResult,
    TokenResult,
    get_auth_api_client,
)

ISSUER = "https://auth.example.test"


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


class FakeAuthClient:
    """In-memory stand-in for the authentication service client."""

    def __init__(self):
        self.registered = []
        self.existing_emails = set()
        self.bad_code = False
        self.bad_credentials = False
        self.mfa_required = False
        self.tokens = None
        self.profile = ProfileResult(sub="user", nickname="ally")
        self.profile_updates = []

    async def register(self, email, password, **kwargs):
        if email in self.existing_emails:
            raise AuthAPIError("Email already registered", "conflict")
        self.registered.append((email, kwargs))
        return RegisterResult(user_id=str(uuid4()), email=email, message="ok")

    async def verify_email(self, email, code):
        if self.bad_code:
            raise AuthAPIError("Invalid verification code")
        return True

    async def login(self, email, password, otp=None):
        if self.mfa_required and not otp:
            raise AuthAPIError("mfa_required", "mfa_required")
        if self.bad_credentials:
            raise AuthAPIError("bad", "invalid_grant")
        return self.tokens

    async def get_userinfo(self, access_token):
        return {"name": "Alice", "email": "alice@example.test", "nickname": "ally"}

    async def forgot_password(self, email, reset_base_url=None):
        raise AuthAPIError("unknown account")

    async def reset_password(self, token, password):
        return True

    async def get_profile(self, access_token):
        return self.profile

    async def update_profile(self, access_token, **fields):
        self.profile_updates.append(fields)
        return self.profile


def _access_token(user_id, name):
    return jwt.encode(
        {"sub": user_id, "name": name, "email": "alice@example.test", "scope": "openid"},
        "unused-secret",
        algorithm="HS256",
    )


@given("the web authentication settings")
def step_settings(context):
    settings = get_settings()
    for name, value in (
        ("oauth2_issuer", ISSUER),
        ("oauth2_frontend_client_id", "web-client"),
        ("oauth2_client_id", "backend-client"),
        ("oauth2_client_secret", "backend-secret"),
        ("app_base_url", "https://app.example.test"),
        ("cookie_secure", False),
        ("cookie_domain", ""),
    ):
        _patch(context, (settings, name), value, attribute=True)


@given("an authentication service")
def step_auth_service(context):
    context.auth_client = FakeAuthClient()
    context.internal_app.dependency_overrides[get_auth_api_client] = lambda: context.auth_client


@given("the web database is in memory")
def step_web_database(context):
    context.store = Store()
    context.session = FakeSession(context.store)

    async def fake_db():
        yield context.session

    context.internal_app.dependency_overrides[get_db] = fake_db


@given("OAuth2 is not configured")
def step_oauth_not_configured(context):
    _patch(context, (get_settings(), "oauth2_issuer"), "", attribute=True)


@given('the identity provider issues tokens for user "{user_id}" named "{name}"')
def step_tokens(context, user_id, name):
    context.user_id = user_id
    context.auth_client.tokens = TokenResult(
        access_token=_access_token(user_id, name),
        refresh_token="refresh-token",
        expires_in=3600,
        token_type="Bearer",
    )


@given('the email "{email}" is already registered')
def step_already_registered(context, email):
    context.auth_client.existing_emails.add(email)


@given("the verification code is wrong")
def step_bad_code(context):
    context.auth_client.bad_code = True


@given("the credentials are wrong")
def step_bad_credentials(context):
    context.auth_client.bad_credentials = True


@given("the account requires a second factor")
def step_mfa(context):
    context.auth_client.mfa_required = True


@given('no account exists for "{email}"')
def step_no_account(context, email):
    pass


@given('I am signed in as "{name}" with the nickname "{nickname}"')
def step_signed_in(context, name, nickname):
    user = User(id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), name=name, nickname=nickname)
    tenant = Organization(id=uuid4(), name="Acme", slug="acme", plan=PlanType.FREE)
    member = OrganizationMember(
        organization_id=tenant.id, user_id=user.id, role=OrganizationMemberRole.OWNER
    )
    context.auth_client.profile = ProfileResult(sub=str(user.id), nickname=nickname, name=name)
    context.internal_app.dependency_overrides[get_web_auth_context] = lambda: WebAuthContext(
        user=user, tenant=tenant, tenant_member=member
    )


# --- requests ---------------------------------------------------------------


def _form(context, method, path, data=None, cookies=None):
    headers = {}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    context.response = context.call(
        method, path, data=data, headers=headers, follow_redirects=False
    )


@when(
    'the identity provider redirects back with state "{state}" while the browser holds state "{held}"'
)
def step_callback_mismatch(context, state, held):
    _form(
        context,
        "GET",
        f"/auth/callback?code=abc&state={state}",
        cookies={"oauth_state": held, "oauth_code_verifier": "verifier"},
    )


@when("the identity provider redirects back with a valid code")
def step_callback_ok(context):
    real_client = httpx.AsyncClient

    def handler(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": context.auth_client.tokens.access_token,
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(
            200, json={"name": "Alice", "email": "alice@example.test", "nickname": None}
        )

    def factory(*args, **kwargs):
        if isinstance(kwargs.get("transport"), httpx.ASGITransport):
            return real_client(*args, **kwargs)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    _patch(context, "knowledge.routes.auth.httpx.AsyncClient", factory)
    _form(
        context,
        "GET",
        "/auth/callback?code=abc&state=expected",
        cookies={
            "oauth_state": "expected",
            "oauth_code_verifier": "verifier",
            "oauth_redirect": "/dashboard",
        },
    )


@when('I sign up as "{email}" with password "{password}" and confirmation "{confirmation}"')
def step_signup(context, email, password, confirmation):
    _form(
        context,
        "POST",
        "/auth/signup",
        data={
            "email": email,
            "password": password,
            "password_confirm": confirmation,
            "nickname": "ally",
            "firstname": "Alice",
            "lastname": "Martin",
            "workspace_name": "Team Space",
        },
    )


@when('I verify "{email}" with the code "{code}"')
def step_verify(context, email, code):
    _form(context, "POST", "/auth/verify", data={"email": email, "code": code})


@when('I sign in as "{email}" with password "{password}"')
def step_signin(context, email, password):
    _form(context, "POST", "/auth/signin", data={"email": email, "password": password})


@when('I sign in as "{email}" using password "{password}" to create the workspace "{workspace}"')
def step_signin_workspace(context, email, password, workspace):
    _form(
        context,
        "POST",
        "/auth/signin",
        data={"email": email, "password": password, "workspace_name": workspace},
    )


@when('I ask for a password reset for "{email}"')
def step_forgot(context, email):
    _form(context, "POST", "/auth/forgot-password", data={"email": email})


@when('I reset the password with the token "{token}" and the new password "{password}"')
def step_reset(context, token, password):
    _form(
        context,
        "POST",
        "/auth/reset-password",
        data={"token": token, "password": password, "password_confirm": password},
    )


@when('I update my profile nickname to "{nickname}"')
def step_update_profile(context, nickname):
    _form(context, "POST", "/auth/account", data={"nickname": nickname})


# --- assertions ---------------------------------------------------------------


@then("I should be redirected to the authorization endpoint of the issuer")
def step_authorization_endpoint(context):
    location = context.response.headers["location"]
    assert location.startswith(f"{ISSUER}/oauth2/authorize?"), location
    context.authorization_query = parse_qs(urlparse(location).query)
    assert context.authorization_query["client_id"] == ["web-client"]
    assert context.authorization_query["redirect_uri"] == ["https://app.example.test/auth/callback"]


@then("the authorization request should use the S256 code challenge method")
def step_pkce(context):
    assert context.authorization_query["code_challenge_method"] == ["S256"]
    assert context.authorization_query["code_challenge"][0]


@then('the authentication service should have registered "{email}"')
def step_registered(context, email):
    assert [e for e, _ in context.auth_client.registered] == [email]


@then('the authentication service should have updated the nickname to "{nickname}"')
def step_nickname_updated(context, nickname):
    assert context.auth_client.profile_updates[0]["nickname"] == nickname


@then('a free workspace "{name}" should have been created for the user')
def step_workspace_created(context, name):
    organizations = list(context.store.organizations.values())
    assert [o.name for o in organizations] == [name], organizations
    assert organizations[0].plan == PlanType.FREE
    members = list(context.store.members.values())
    assert [(m.user_id, m.role) for m in members] == [
        (UUID(context.user_id), OrganizationMemberRole.OWNER)
    ]
