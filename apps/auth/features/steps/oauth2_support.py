# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Helpers shared by the OAuth2 related step modules (no step definitions here)."""

import asyncio
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

from auth.services.oauth2_client import OAuth2ClientService

REDIRECT_URI = "https://app.example.com/callback"
STATE = "xyz"
NONCE = "n-0S6"
AUTH_CODE_GRANTS = ["authorization_code", "refresh_token", "client_credentials"]


def create_client(
    context, name, scopes, *, confidential, consent, grants=AUTH_CODE_GRANTS, pkce=True
):
    """Register an OAuth2 client and remember its credentials under ``name``."""
    client, secret = asyncio.run(
        OAuth2ClientService().create_client(
            context.db,
            name=name,
            redirect_uris=[REDIRECT_URI],
            allowed_scopes=scopes.split(),
            allowed_grant_types=grants,
            is_confidential=confidential,
            require_pkce=pkce,
            require_consent=consent,
            allowed_origins=["https://app.example.com"],
        )
    )
    context.clients = getattr(context, "clients", {})
    context.clients[name] = {"client_id": client.client_id, "secret": secret}
    context.current_client = name
    return client


def client_of(context, name=None):
    return context.clients[name or context.current_client]


def new_pkce(context):
    context.verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(context.verifier.encode()).digest()
    context.challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")


def authorization_params(context, *, client_id, redirect_uri, scopes, pkce=True):
    new_pkce(context)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": STATE,
        "nonce": NONCE,
    }
    if pkce:
        params.update(code_challenge=context.challenge, code_challenge_method="S256")
    return params


def authorize(context, *, client_id, redirect_uri, scopes, pkce=True):
    """Send an authorization request and remember the code of a successful redirect."""
    params = authorization_params(
        context, client_id=client_id, redirect_uri=redirect_uri, scopes=scopes, pkce=pkce
    )
    context.authorize_params = params
    context.response = context.client.get(
        "/oauth2/authorize", params=params, follow_redirects=False
    )
    remember_code(context)


def remember_code(context):
    location = context.response.headers.get("location", "")
    if context.response.status_code == 302 and location.startswith(REDIRECT_URI):
        context.code = parse_qs(urlparse(location).query).get("code", [None])[0]


def token_request(context, data, *, secret="__client__"):
    """POST to the token endpoint, authenticating as the current client."""
    client = client_of(context)
    auth = None
    form = dict(data)
    if client["secret"] is not None and secret is not None:
        auth = (client["client_id"], client["secret"] if secret == "__client__" else secret)
    else:
        form["client_id"] = client["client_id"]
    context.response = context.client.post("/oauth2/token", data=form, auth=auth)
    if context.response.status_code == 200:
        context.tokens = context.response.json()
    return context.response
