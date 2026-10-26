# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The stack behind the ``@browser`` scenarios.

A real browser talks to a real server, so the application is served by ``LiveServer`` in a
thread of the behave process (next to the fake OpenID provider of ``e2e-support``). Every
service the application depends on is replaced by a stand-in patched in-process:

- the database is a SQLite file per scenario (``browser_db``);
- the identity provider is ``FakeOIDCProvider``: ``/auth/login`` is a genuine PKCE login,
  the tokens are signed by the provider and validated by the application against its JWKS,
  introspection and token exchange endpoints, and the users' scopes decide what the
  application grants;
- the authentication service of the sign-up and sign-in pages (``browser_auth``);
- the services the pages of a feature call (billing, mailler, custom-domain, the embedding
  model) are in-memory fakes that the step modules of the feature install with
  ``scenario_setup``; the steps reach them as ``context.stack.billing``, ``.mailbox``, ...

The provider and the server start with the first ``@browser`` scenario that runs and stop
with the run; the settings, the fakes and the database are rebuilt for each scenario.
"""

import uuid
from contextlib import ExitStack
from unittest.mock import patch

from browser_auth import FakeAuthService
from browser_db import Database
from e2e_support import behave_hooks as e2e
from e2e_support.oidc import Client, FakeOIDCProvider, User

from knowledge.auth import jwt as jwt_module
from knowledge.auth import token_exchange as token_exchange_module
from knowledge.config import get_settings
from knowledge.database import get_db
from knowledge.services.auth_api import get_auth_api_client

#: The OAuth2 clients the application is configured with (they only exist in the provider).
FRONTEND_CLIENT_ID = "knowledge-web"
SERVICE_CLIENT_ID = "knowledge-service"
SERVICE_CLIENT_SECRET = "knowledge-service-secret"
#: Scopes the application asks the provider to grant through the token exchange.
API_SCOPES = (
    "collections:read",
    "collections:write",
    "collections:search",
    "documents:read",
    "documents:write",
)
#: Password of every user of the scenarios.
PASSWORD = "Correct-horse-battery-9!"
#: Fail-safe plan limits of the scenarios (billing is not configured, so these apply).
PLAN_LIMITS = {
    "*": {
        "max_collections": 3,
        "max_total_documents": 20,
        "max_documents_per_collection": 10,
        "max_api_calls_per_month": 100,
        "max_storage_bytes": 1048576,
    }
}


class MemoryRedis:
    """The few Redis commands the token exchange cache uses."""

    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value

    async def aclose(self):
        return None


#: Setups the step modules register: called with (stack, scenario) at the start of a scenario
#: to install the fakes and the patches that only their pages need.
SCENARIO_SETUPS = []


def scenario_setup(function):
    """Register ``function(stack, scenario)``: ``scenario`` is the ExitStack of the scenario."""
    SCENARIO_SETUPS.append(function)
    return function


def patch_setting(name, value):
    """Patch a setting for the duration of a scenario."""
    return patch.object(get_settings(), name, value)


def persona_id(email: str) -> str:
    """A stable user id for an email address."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mailto:{email}"))


class Stack:
    """Everything the browser scenarios share; one instance per run."""

    def __init__(self, context):
        self.provider = FakeOIDCProvider(
            clients=[
                Client.service(
                    SERVICE_CLIENT_ID,
                    SERVICE_CLIENT_SECRET,
                    ["openid", "profile", "email", "introspect", "collections:*", "documents:*"],
                )
            ]
        )
        self.issuer = e2e.live_server(context, "provider", self.provider).url
        self.server = e2e.live_server(context, "app", context.app)
        self.url = self.server.url
        self.frontend = Client.public(FRONTEND_CLIENT_ID, [f"{self.url}/auth/callback"])
        self.provider.add_client(self.frontend)
        self.settings = (
            ("oauth2_issuer", self.issuer),
            ("oauth2_frontend_client_id", FRONTEND_CLIENT_ID),
            ("oauth2_client_id", SERVICE_CLIENT_ID),
            ("oauth2_client_secret", SERVICE_CLIENT_SECRET),
            ("app_base_url", self.url),
            ("cookie_secure", False),
            ("cookie_domain", ""),
            ("quota_fallback_limits", PLAN_LIMITS),
        )


def begin_scenario(context):
    """Build what one scenario needs and return the address of the application."""
    state = context.e2e
    if getattr(state, "stack", None) is None:
        state.stack = Stack(context)
    stack = state.stack
    context.stack = stack

    # a clean provider, as a fresh user agent meets it
    provider = stack.provider
    provider.users.clear()
    provider.store.access_tokens.clear()
    provider.store.refresh_tokens.clear()
    provider.end_sessions()
    provider.clear_requests()
    provider.auto_approve = False

    scenario = ExitStack()
    stack.scenario = scenario
    for name, value in stack.settings:
        scenario.enter_context(patch_setting(name, value))
    stack.db = Database()
    scenario.callback(stack.db.dispose)
    stack.auth_service = FakeAuthService(provider, stack.frontend)

    # singletons that remember the issuer or hold a connection of the server's loop
    for module, name in (
        (jwt_module, "_jwt_validator"),
        (token_exchange_module, "_token_exchange_client"),
    ):
        scenario.enter_context(patch.object(module, name, None))
    scenario.enter_context(
        patch.object(token_exchange_module.redis, "from_url", lambda *a, **k: MemoryRedis())
    )

    for app in (context.app, context.internal_app):
        app.dependency_overrides[get_db] = stack.db.dependency
    context.internal_app.dependency_overrides[get_auth_api_client] = lambda: stack.auth_service

    for setup in SCENARIO_SETUPS:
        setup(stack, scenario)
    context.add_cleanup(end_scenario, context)
    return stack.url


def end_scenario(context):
    stack = getattr(context.e2e, "stack", None)
    if stack is None or getattr(stack, "scenario", None) is None:
        return
    for app in (context.app, context.internal_app):
        app.dependency_overrides.clear()
    scenario, stack.scenario = stack.scenario, None
    scenario.close()


def add_user(context, name, scopes=(), email=None):
    """Register a user with the provider (what an administrator of the auth service does)."""
    email = email or f"{name.lower()}@example.test"
    user = User(
        email=email,
        name=name,
        password=PASSWORD,
        scopes=tuple(scopes),
        id=persona_id(email),
    )
    return context.stack.provider.add_user(user)
