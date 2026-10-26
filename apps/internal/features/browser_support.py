# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Stack behind the ``@browser`` scenarios of the internal application.

``install`` wraps the hooks of ``environment.py`` so that the scenarios tagged ``@browser``
(``features/browser``) get a Playwright page next to the in-process setup.

The application is served on a real socket by ``e2e_support`` and users log in
through the fake OpenID provider of the same library, so the OAuth2 login, the
token validation (JWKS, introspection) and the token exchange are the real code
talking to a real HTTP server. What stays in-process is what the other scenarios
already replace: the database (a throw-away SQLite file) and the clients of the
other services (mocks patched on the route modules, which the server thread shares).
"""

import asyncio
import threading
from html import escape
from unittest.mock import patch
from urllib.parse import urljoin, urlsplit

from e2e_support import behave_hooks as e2e
from e2e_support.oidc import Client, FakeOIDCProvider
from internal.auth.jwt import JWTValidator, jwt_validator
from internal.config import settings
from internal.services.token_exchange import TokenExchangeClient, token_exchange_client
from playwright.sync_api import Error as PlaywrightError

#: Credentials of the confidential client the application uses for introspection and
#: token exchange, and id of the public client of its HTML pages (fake provider only).
SERVICE_CLIENT_ID = "internal-browser-service"
SERVICE_CLIENT_SECRET = "internal-browser-secret"
FRONTEND_CLIENT_ID = "internal-browser-frontend"
#: Password of every user the scenarios create at the fake provider.
USER_PASSWORD = "browser-password"

#: Host of the servers of the run (see ``e2e_support.server.LiveServer``).
LOOPBACK = "127.0.0.1"

#: Originals of the objects the in-process environment replaces with mocks.
_REAL_JWT = {
    "validate_token": JWTValidator.validate_token,
    "validate_token_with_introspection": JWTValidator.validate_token_with_introspection,
    "introspect_token": JWTValidator.introspect_token,
}
_REAL_IS_CONFIGURED = TokenExchangeClient.is_configured.fget
_REAL_EXCHANGE = {
    "validate_token_scopes": TokenExchangeClient.validate_token_scopes,
    "exchange_token": TokenExchangeClient.exchange_token,
}

_patches: list = []


def _forward(function, instance):
    """An async side effect calling the original ``function`` on ``instance``."""

    async def call(*args, **kwargs):
        return await function(instance, *args, **kwargs)

    return call


def _provider(context) -> FakeOIDCProvider:
    return context.e2e.servers["provider"].app


def provider(context) -> FakeOIDCProvider:
    """The fake OpenID provider of the run (valid inside a ``@browser`` scenario)."""
    return _provider(context)


def _start_servers(context, app) -> None:
    servers = context.e2e.servers
    if "provider" in servers:
        return
    fake = FakeOIDCProvider(
        clients=[
            Client.service(SERVICE_CLIENT_ID, SERVICE_CLIENT_SECRET, ["openid", "introspect", "*"])
        ]
    )
    e2e.live_server(context, "provider", fake)
    server = e2e.live_server(context, "app", app)
    fake.add_client(Client.public(FRONTEND_CLIENT_ID, [f"{server.url}/auth/callback"]))


def start(context, app) -> str:
    """Serve the provider and the application, point the application at the provider.

    Called once per ``@browser`` scenario, lazily (nothing starts when browser scenarios
    are skipped). Returns the URL of the application.
    """
    _start_servers(context, app)
    servers = context.e2e.servers
    fake = _provider(context)
    fake.users.clear()
    fake.require_consent = False
    fake.end_sessions()
    fake.revoke_tokens()
    fake.clear_requests()

    overrides = {
        "oauth2_issuer": servers["provider"].url,
        "oauth2_client_id": SERVICE_CLIENT_ID,
        "oauth2_client_secret": SERVICE_CLIENT_SECRET,
        "oauth2_frontend_client_id": FRONTEND_CLIENT_ID,
        "app_base_url": servers["app"].url,
        "cookie_secure": False,
        "redis_url": "",  # no cache: every request is validated by the provider
    }
    for name, value in overrides.items():
        patcher = patch.object(settings, name, value)
        patcher.start()
        _patches.append(patcher)

    # The in-process environment mocks the validator and the token exchange; the real
    # implementations run here, against the provider.
    context.mock_jwt_validate.side_effect = _forward(_REAL_JWT["validate_token"], jwt_validator)
    context.mock_jwt_validate_introspect.side_effect = _forward(
        _REAL_JWT["validate_token_with_introspection"], jwt_validator
    )
    context.mock_jwt_introspect_active.side_effect = _forward(
        _REAL_JWT["introspect_token"], jwt_validator
    )
    context.mock_exchange_configured.side_effect = lambda: _REAL_IS_CONFIGURED(
        token_exchange_client
    )
    context.mock_exchange_validate.side_effect = _forward(
        _REAL_EXCHANGE["validate_token_scopes"], token_exchange_client
    )
    context.mock_exchange_exchange.side_effect = _forward(
        _REAL_EXCHANGE["exchange_token"], token_exchange_client
    )
    return servers["app"].url


def block_external(browser_context) -> None:
    """Keep the browser on the servers of the run.

    A scenario must neither need nor reach the network. A request to another host is
    answered with a stub: an empty script or stylesheet (the pages must work without a
    CDN) or, for a page, a stub saying which address was requested. A redirect of the
    application to another host (to Stripe, to a SaaS application) gets the same stub:
    the browser does not offer the redirects it follows to the route handlers, so the
    responses of the application are inspected.
    """

    def stub(route, url: str) -> None:
        stubs = {"script": "application/javascript", "stylesheet": "text/css"}
        kind = route.request.resource_type
        if kind in stubs:
            route.fulfill(status=200, content_type=stubs[kind], body="")
        elif kind == "document":
            route.fulfill(
                status=200,
                content_type="text/html",
                body=f"<title>External</title><h1>External site</h1><p>{escape(url)}</p>",
            )
        else:
            route.abort()

    def handle(route) -> None:
        url = route.request.url
        if urlsplit(url).hostname != LOOPBACK:
            stub(route, url)
            return
        try:
            response = route.fetch(max_redirects=0)
            location = response.headers.get("location")
            if location and 300 <= response.status < 400:
                target = urljoin(url, location)
                if urlsplit(target).hostname != LOOPBACK:
                    stub(route, target)
                    return
            route.fulfill(response=response)
        except PlaywrightError:
            # The page went away while the application was answering (end of a scenario)
            return

    browser_context.route("**/*", handler=handle)


def is_active() -> bool:
    """Whether :func:`start` ran for the current scenario."""
    return bool(_patches)


def stop(context) -> None:
    """Undo :func:`start`: settings back, auth mocks back to the in-process behavior."""
    while _patches:
        _patches.pop().stop()
    for mock in (
        context.mock_jwt_validate,
        context.mock_jwt_validate_introspect,
        context.mock_jwt_introspect_active,
        context.mock_exchange_configured,
        context.mock_exchange_validate,
        context.mock_exchange_exchange,
    ):
        mock.side_effect = None


class BackgroundLoop:
    """An event loop running in its own thread, driven like ``run_until_complete``.

    The sync Playwright API keeps an event loop running in the thread of the scenarios,
    so the steps cannot start one there: they hand their coroutines to this loop.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="behave-loop", daemon=True
        )
        self._thread.start()

    def run_until_complete(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def is_closed(self) -> bool:
        return self._loop.is_closed()

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()


def install(environment: dict) -> None:
    """Wrap the hooks of the environment module (its ``globals()``) with the browser ones."""
    app = environment["app"]
    hooks = {
        name: environment[name]
        for name in ("before_all", "before_scenario", "after_scenario", "after_all")
    }

    def before_all(context):
        e2e.before_all(context)
        hooks["before_all"](context)
        # The loop the steps run coroutines on must not be the thread's: Playwright's sync
        # API keeps that one running
        context.loop.close()
        context.loop = BackgroundLoop()

    def before_scenario(context, scenario):
        hooks["before_scenario"](context, scenario)
        # Serves the application and the provider lazily, only when the scenario really runs
        e2e.before_scenario(context, scenario, base_url=lambda: start(context, app))
        if getattr(context, "browser_context", None) is not None:
            block_external(context.browser_context)

    def after_scenario(context, scenario):
        # Requests of the page still in flight (a live preview, a poll) are answered by routes
        # that must not outlive the scenario: they would fail while the next one starts
        browser_context = getattr(context, "browser_context", None)
        if browser_context is not None:
            browser_context.unroute_all(behavior="ignoreErrors")
        e2e.after_scenario(context, scenario)
        if is_active():
            stop(context)
        hooks["after_scenario"](context, scenario)

    def after_all(context):
        e2e.after_all(context)
        hooks["after_all"](context)

    environment.update(
        before_all=before_all,
        before_scenario=before_scenario,
        after_scenario=after_scenario,
        after_all=after_all,
    )
