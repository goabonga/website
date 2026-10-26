# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A fake OpenID provider, served by :class:`~e2e_support.server.LiveServer`.

It stands in for the auth application of this repository so that an application that logs
users in through OpenID Connect can be exercised, in a browser, with no real identity
provider. Endpoints follow the auth application: ``/.well-known/openid-configuration``,
``/.well-known/jwks.json``, ``/oauth2/authorize``, ``/oauth2/token``, ``/oauth2/introspect``,
``/oauth2/revoke`` and ``/userinfo``.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from e2e_support.oidc import authorize
from e2e_support.oidc.keys import SigningKey
from e2e_support.oidc.models import (
    AUTHORIZATION_CODE,
    CLIENT_CREDENTIALS,
    OIDC_SCOPES,
    REFRESH_TOKEN,
    TOKEN_EXCHANGE,
    Client,
    RecordedRequest,
    User,
)
from e2e_support.oidc.recording import RecordingMiddleware
from e2e_support.oidc.store import Store

#: Default lifetime of an access token, in seconds.
ACCESS_TOKEN_TTL = 3600
#: Default lifetime of a refresh token, in seconds.
REFRESH_TOKEN_TTL = 30 * 24 * 3600
#: Default lifetime of an authorization code, in seconds.
CODE_TTL = 600
#: Default lifetime of an ID token, in seconds.
ID_TOKEN_TTL = 3600


class FakeOIDCProvider:
    """An in-memory OpenID provider with configurable users and clients.

    ``issuer`` is the public base URL. Leave it out when the provider is served by a
    :class:`~e2e_support.server.LiveServer`: the server tells the provider its URL. The
    issuer must not have a path component.

    With ``auto_approve`` the authorization endpoint logs the first user in (or the one named
    by ``login_hint``) without showing any page; otherwise it shows a minimal login page and,
    with ``require_consent``, a consent page. ``pairwise_subjects`` derives a different
    ``sub`` per client, like the auth application, instead of the plain user id.
    """

    def __init__(
        self,
        users: Iterable[User] = (),
        clients: Iterable[Client] = (),
        *,
        issuer: str | None = None,
        auto_approve: bool = False,
        require_consent: bool = False,
        pairwise_subjects: bool = False,
        access_token_ttl: int = ACCESS_TOKEN_TTL,
        refresh_token_ttl: int = REFRESH_TOKEN_TTL,
        code_ttl: int = CODE_TTL,
        id_token_ttl: int = ID_TOKEN_TTL,
        signing_key: SigningKey | None = None,
    ) -> None:
        self.users: dict[str, User] = {}
        self.clients: dict[str, Client] = {}
        for user in users:
            self.add_user(user)
        for client in clients:
            self.add_client(client)
        self._issuer = issuer.rstrip("/") if issuer else None
        self.auto_approve = auto_approve
        self.require_consent = require_consent
        self.pairwise_subjects = pairwise_subjects
        self.access_token_ttl = access_token_ttl
        self.refresh_token_ttl = refresh_token_ttl
        self.code_ttl = code_ttl
        self.id_token_ttl = id_token_ttl
        self.key = signing_key or SigningKey()
        self.store = Store()
        self.clock = time.time
        self.requests: list[RecordedRequest] = []
        self.app = self._build_app()
        self._asgi = RecordingMiddleware(self.app, self.requests)

    # -- configuration ---------------------------------------------------------------

    @property
    def issuer(self) -> str:
        """The issuer URL; known once the provider is served or given explicitly."""
        if self._issuer is None:
            raise RuntimeError(
                "the issuer is not known yet: serve the provider with LiveServer or pass issuer=..."
            )
        return self._issuer

    def bind_url(self, url: str) -> None:
        """Called by :class:`~e2e_support.server.LiveServer` with the public URL."""
        self._issuer = url.rstrip("/")

    def add_user(self, user: User) -> User:
        self.users[user.id] = user
        return user

    def add_client(self, client: Client) -> Client:
        self.clients[client.client_id] = client
        return client

    def now(self) -> float:
        """The current time, in seconds since the epoch (``clock`` can be replaced in tests)."""
        return self.clock()

    def user_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email.lower() == email.lower()), None)

    # -- recorded requests -----------------------------------------------------------

    def requests_to(self, path: str, method: str | None = None) -> list[RecordedRequest]:
        """The recorded requests for ``path`` (and ``method``), oldest first."""
        return [
            r
            for r in self.requests
            if r.path == path and (method is None or r.method == method.upper())
        ]

    def last_request(self, path: str) -> RecordedRequest:
        """The latest recorded request for ``path``; ``LookupError`` when there is none."""
        matching = self.requests_to(path)
        if not matching:
            raise LookupError(f"the provider received no request for {path}")
        return matching[-1]

    def clear_requests(self) -> None:
        self.requests.clear()

    def end_sessions(self) -> None:
        """Forget every logged-in session: the next authorization asks for a login again."""
        self.store.sessions.clear()

    # -- ASGI ------------------------------------------------------------------------

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        await self._asgi(scope, receive, send)

    def base_url(self, request: Request) -> str:
        """The issuer, or the address the request used when none is configured."""
        return self._issuer or str(request.base_url).rstrip("/")

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @app.get("/.well-known/openid-configuration")
        async def discovery(request: Request) -> JSONResponse:
            return JSONResponse(self.discovery_document(self.base_url(request)))

        @app.get("/.well-known/jwks.json")
        async def jwks() -> JSONResponse:
            return JSONResponse({"keys": [self.key.public_jwk()]})

        authorize.install(self, app)
        return app

    def discovery_document(self, issuer: str) -> dict[str, Any]:
        """The OpenID Connect discovery document, with the same fields as the auth app."""
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth2/authorize",
            "token_endpoint": f"{issuer}/oauth2/token",
            "userinfo_endpoint": f"{issuer}/userinfo",
            "jwks_uri": f"{issuer}/.well-known/jwks.json",
            "revocation_endpoint": f"{issuer}/oauth2/revoke",
            "introspection_endpoint": f"{issuer}/oauth2/introspect",
            "scopes_supported": list(OIDC_SCOPES),
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": [
                AUTHORIZATION_CODE,
                REFRESH_TOKEN,
                CLIENT_CREDENTIALS,
                TOKEN_EXCHANGE,
            ],
            "subject_types_supported": ["pairwise" if self.pairwise_subjects else "public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
                "none",
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
            "claims_supported": [
                "sub",
                "iss",
                "aud",
                "exp",
                "iat",
                "auth_time",
                "nonce",
                "name",
                "email",
                "email_verified",
            ],
        }
