# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The stack behind the ``@browser`` scenarios.

The application and a fake OpenID provider (``e2e_support.oidc``) listen on
real sockets, once per run. The application is pointed at the provider through
its settings, exactly like a deployment points it at the ``auth`` service, so
the login, the token validation and the user profile all go through HTTP.
"""

from urllib.parse import urlparse

from apt_server.auth import introspection_client, jwks_manager, userinfo_client
from apt_server.config import settings
from apt_server.main import app
from e2e_support import behave_hooks as e2e
from e2e_support.oidc import Client, FakeOIDCProvider

#: Hosts of the servers started by the stack.
LOOPBACK = ("127.0.0.1", "localhost")

#: Client the web login uses (public, PKCE), as ``OAUTH2_SWAGGER_CLIENT_ID``.
WEB_CLIENT_ID = "apt-web"
#: Service client the application introspects tokens with.
SERVICE_CLIENT_ID = "apt-server"
SERVICE_CLIENT_SECRET = "apt-server-secret"
SESSION_SECRET = "apt-session-secret"


def provider_of(context) -> FakeOIDCProvider:
    return context.e2e.servers["provider"].app


def _use_fresh_http_clients() -> None:
    """Drop the HTTP clients that earlier in-process scenarios may have created.

    The application runs in the server thread, on its own event loop, and an
    ``httpx.AsyncClient`` is bound to the loop it was first used in.
    """
    for client in (jwks_manager, introspection_client, userinfo_client):
        client._http_client = None


def forget_identity_provider() -> None:
    """Forget the discovery document and the keys cached from the fake provider."""
    jwks_manager._issuer_config = None
    jwks_manager._jwks_client = None


def serve(context, scenario) -> str:
    """Start the stack on first use, reset the provider and return the application URL."""
    servers = context.e2e.servers
    if "provider" not in servers:
        provider = FakeOIDCProvider(
            clients=[
                Client.service(
                    SERVICE_CLIENT_ID,
                    SERVICE_CLIENT_SECRET,
                    ["openid", "profile", "email", "introspect"],
                )
            ]
        )
        # The provider first, so that its URL can go into the application settings
        e2e.live_server(context, "provider", provider)
        url = e2e.live_server(context, "app", app).url
        # The redirect URI is only known once the application listens
        provider.add_client(Client.public(WEB_CLIENT_ID, [f"{url}/callback"]))
        _use_fresh_http_clients()

    provider = provider_of(context)
    provider.users.clear()
    provider.end_sessions()
    provider.revoke_tokens()
    provider.clear_requests()

    context.patch(settings, "oauth2_issuer", provider.issuer)
    context.patch(settings, "oauth2_client_id", SERVICE_CLIENT_ID)
    context.patch(settings, "oauth2_client_secret", SERVICE_CLIENT_SECRET)
    context.patch(settings, "oauth2_swagger_client_id", WEB_CLIENT_ID)
    context.patch(settings, "session_secret", SESSION_SECRET)
    context.patch(settings, "apt_gpg_key_id", "")
    return servers["app"].url


#: A transparent pixel, served in place of the avatars hosted by third parties.
PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def keep_to_the_stack(context, scenario) -> None:
    """Let a browser scenario reach the application and the provider only.

    The pages show an avatar hosted by a third party when the identity provider gives none;
    it is answered with a pixel so that a scenario needs no network, and any other request
    to a third party fails, which the scenario reports as a browser error. The requests to
    the servers of the scenario are not intercepted.
    """
    if "browser" not in scenario.effective_tags or getattr(context, "page", None) is None:
        return

    def handle(route):
        if route.request.resource_type == "image":
            route.fulfill(status=200, content_type="image/gif", body=PIXEL)
        else:
            route.abort()

    context.browser_context.route(lambda url: urlparse(url).hostname not in LOOPBACK, handle)
