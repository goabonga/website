# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Users, clients and recorded requests of the fake OpenID provider."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

#: Scopes every client may use unless it is restricted further.
OIDC_SCOPES = ("openid", "profile", "email", "offline_access")

AUTHORIZATION_CODE = "authorization_code"
REFRESH_TOKEN = "refresh_token"
CLIENT_CREDENTIALS = "client_credentials"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"

#: Scope a client needs to call the introspection endpoint (same rule as the auth app).
INTROSPECT_SCOPE = "introspect"


#: Resources covered by the ``internal:*`` wildcard of a token exchange.
INTERNAL_RESOURCES = ("namespaces", "prompts", "knowledge", "conversations")


def client_scope_matches(scope: str, allowed: Iterable[str]) -> bool:
    """Whether ``scope`` is permitted by the client's ``allowed`` scopes.

    Same rule as the auth application when it validates the scopes of a client: an
    exact match, ``*``, or a hierarchical wildcard (``billing:*`` allows ``billing:read``
    and ``billing:invoices:read``).
    """
    allowed = list(allowed)
    if scope in allowed or "*" in allowed:
        return True
    parts = scope.split(":")
    return any(":".join(parts[:i]) + ":*" in allowed for i in range(len(parts) - 1, 0, -1))


def exchange_scope_matches(scope: str, allowed: Iterable[str]) -> bool:
    """Whether a client's ``allowed`` scopes let it request ``scope`` in a token exchange.

    The auth application filters exchange requests with a single-level rule: exact match,
    ``*``, ``<resource>:*``, and ``internal:*`` for the internal resources.
    """
    resource = scope.split(":")[0] if ":" in scope else scope
    for pattern in allowed:
        if pattern in ("*", scope, f"{resource}:*"):
            return True
        if pattern == "internal:*" and resource in INTERNAL_RESOURCES:
            return True
    return False


def user_has_scope(user_scopes: Iterable[str], required: str) -> bool:
    """Whether a user's role scopes grant ``required`` (``*``, exact or ``<resource>:*``)."""
    resource = required.split(":")[0]
    return any(scope in ("*", required, f"{resource}:*") for scope in user_scopes)


@dataclass
class User:
    """A person who can log in through the provider.

    ``scopes`` are the permissions the user holds through roles in the real auth
    application. They never appear in the tokens of a plain login (only the OIDC scopes
    do): an application obtains them through a token exchange, which grants the requested
    scopes that the user holds.

    ``mfa`` only accepts ``"none"``: multi-factor flows are not emulated.
    """

    email: str
    name: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scopes: tuple[str, ...] = ()
    password: str | None = None
    mfa: str = "none"
    email_verified: bool = True
    picture: str | None = None

    def __post_init__(self) -> None:
        if self.mfa != "none":
            raise ValueError(f"mfa={self.mfa!r} is not supported: only 'none' is emulated")
        self.scopes = tuple(self.scopes)
        try:
            uuid.UUID(self.id)
        except ValueError:
            raise ValueError(f"user id {self.id!r} must be a UUID, like in the auth app") from None


@dataclass
class Client:
    """An OAuth2 client registered with the provider.

    A client with a ``client_secret`` is confidential and must authenticate (Basic or
    form fields); without one it is public. ``redirect_uris`` are exact URIs, or patterns
    where ``*`` matches any characters (``http://127.0.0.1:*/auth/callback``, handy when the
    application listens on a random port); an empty list accepts any redirect URI.
    ``allowed_scopes`` may contain wildcards (``billing:*``, ``*``).
    """

    client_id: str
    client_secret: str | None = None
    redirect_uris: tuple[str, ...] = ()
    allowed_scopes: tuple[str, ...] = ("openid", "profile", "email", "offline_access")
    grant_types: tuple[str, ...] = (AUTHORIZATION_CODE, REFRESH_TOKEN)
    require_pkce: bool = True
    access_token_ttl: int | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        self.redirect_uris = tuple(self.redirect_uris)
        self.allowed_scopes = tuple(self.allowed_scopes)
        self.grant_types = tuple(self.grant_types)

    @property
    def is_confidential(self) -> bool:
        return bool(self.client_secret)

    @classmethod
    def public(cls, client_id: str, redirect_uris: Iterable[str] = (), **options: Any) -> Client:
        """A public PKCE client, like the browser front ends of the applications."""
        return cls(client_id, None, tuple(redirect_uris), **options)

    @classmethod
    def service(
        cls, client_id: str, client_secret: str, allowed_scopes: Iterable[str], **options: Any
    ) -> Client:
        """A confidential service client: client credentials, token exchange, introspection.

        ``allowed_scopes`` must list ``introspect`` for the client to call ``/oauth2/introspect``.
        """
        options.setdefault("grant_types", (CLIENT_CREDENTIALS, TOKEN_EXCHANGE, REFRESH_TOKEN))
        return cls(client_id, client_secret, (), tuple(allowed_scopes), **options)


@dataclass(frozen=True)
class RecordedRequest:
    """A request received by the provider, kept for assertions."""

    method: str
    path: str
    query: dict[str, str]
    form: dict[str, str]
    headers: dict[str, str]
    status: int
    response_body: bytes

    @property
    def json(self) -> Any:
        """The JSON body of the response (``None`` when it is not JSON)."""
        try:
            return json.loads(self.response_body)
        except ValueError:
            return None

    @property
    def params(self) -> dict[str, str]:
        """Query and form parameters together (form values win)."""
        return {**self.query, **self.form}
