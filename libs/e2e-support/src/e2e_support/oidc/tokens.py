# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Issuing access, refresh and ID tokens, with the claims of the auth application."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from typing import TYPE_CHECKING, Any

from e2e_support.oidc.models import Client
from e2e_support.oidc.store import AccessTokenRecord, RefreshTokenRecord

if TYPE_CHECKING:
    from e2e_support.oidc.provider import FakeOIDCProvider


def subject_for(provider: FakeOIDCProvider, user_id: str | None, client: Client) -> str:
    """The ``sub`` claim: the client id without a user, else the user id (pairwise on demand)."""
    if user_id is None:
        return client.client_id
    if provider.pairwise_subjects:
        return str(uuid.uuid5(uuid.UUID(user_id), client.client_id))
    return user_id


def access_token_ttl(provider: FakeOIDCProvider, client: Client) -> int:
    return (
        client.access_token_ttl
        if client.access_token_ttl is not None
        else provider.access_token_ttl
    )


def issue_access_token(
    provider: FakeOIDCProvider,
    client: Client,
    scopes: list[str],
    issuer: str,
    *,
    user_id: str | None = None,
    nonce: str | None = None,
    audience: str | None = None,
    actor: dict[str, Any] | None = None,
) -> str:
    """Sign an access token and remember it so that it can be introspected and revoked."""
    now = int(provider.now())
    ttl = access_token_ttl(provider, client)
    jti = str(uuid.uuid4())
    claims: dict[str, Any] = {
        "iss": issuer,
        "sub": subject_for(provider, user_id, client),
        "aud": audience or client.client_id,
        "exp": now + ttl,
        "iat": now,
        "jti": jti,
        "scope": " ".join(scopes),
        "client_id": client.client_id,
    }
    if nonce:
        claims["nonce"] = nonce
    if actor:
        claims["act"] = actor
    provider.store.access_tokens[jti] = AccessTokenRecord(
        jti=jti,
        client_id=client.client_id,
        user_id=user_id,
        scopes=list(scopes),
        expires_at=now + ttl,
    )
    return provider.key.sign(claims)


def issue_refresh_token(
    provider: FakeOIDCProvider, client: Client, scopes: list[str], user_id: str | None
) -> str:
    token = secrets.token_urlsafe(48)
    provider.store.refresh_tokens[token] = RefreshTokenRecord(
        token=token,
        client_id=client.client_id,
        user_id=user_id,
        scopes=list(scopes),
        expires_at=provider.now() + provider.refresh_token_ttl,
    )
    return token


def issue_id_token(
    provider: FakeOIDCProvider,
    client: Client,
    user_id: str,
    issuer: str,
    *,
    nonce: str | None,
    auth_time: int | None,
    access_token: str,
) -> str:
    """An ID token with ``at_hash`` (half of the SHA-256 of the access token)."""
    now = int(provider.now())
    digest = hashlib.sha256(access_token.encode()).digest()
    claims: dict[str, Any] = {
        "iss": issuer,
        "sub": subject_for(provider, user_id, client),
        "aud": client.client_id,
        "exp": now + provider.id_token_ttl,
        "iat": now,
        "at_hash": base64.urlsafe_b64encode(digest[:16]).rstrip(b"=").decode(),
    }
    if nonce:
        claims["nonce"] = nonce
    if auth_time:
        claims["auth_time"] = auth_time
    return provider.key.sign(claims)
