# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The token endpoint: authorization code, refresh token, client credentials, token exchange.

Behavior, checks and error codes follow ``/oauth2/token`` of the auth application. In
particular the **token exchange** grants the scopes that are requested, allowed for the
exchanging client *and* held by the user (in the subject token, or among the user's role
scopes), exactly like the real service.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING, Any

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from e2e_support.oidc import pkce, tokens
from e2e_support.oidc.client_auth import authenticate
from e2e_support.oidc.errors import OAuthError
from e2e_support.oidc.http import read_form
from e2e_support.oidc.models import (
    AUTHORIZATION_CODE,
    CLIENT_CREDENTIALS,
    REFRESH_TOKEN,
    TOKEN_EXCHANGE,
    Client,
    client_scope_matches,
    exchange_scope_matches,
    user_has_scope,
)

if TYPE_CHECKING:
    from e2e_support.oidc.provider import FakeOIDCProvider

TOKEN_TYPE_ACCESS_TOKEN = "urn:ietf:params:oauth:token-type:access_token"
TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"
SUBJECT_TOKEN_TYPES = (TOKEN_TYPE_ACCESS_TOKEN, TOKEN_TYPE_JWT)


def _response(access_token: str, expires_in: int, scopes: list[str], **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": " ".join(scopes) or None,
        **extra,
    }
    return JSONResponse({key: value for key, value in body.items() if value is not None})


def install(provider: FakeOIDCProvider, app: FastAPI) -> None:
    """Add ``POST /oauth2/token`` to ``app``."""

    @app.exception_handler(OAuthError)
    async def oauth_error(_request: Request, error: OAuthError) -> JSONResponse:
        return error.response()

    @app.post("/oauth2/token")
    async def token(request: Request) -> JSONResponse:
        form = await read_form(request)
        client = authenticate(
            provider,
            request.headers.get("authorization"),
            form,
            missing_id_is_invalid_request=True,
        )
        grant_type = form.get("grant_type", "")
        if grant_type not in client.grant_types:
            raise OAuthError(
                "unauthorized_client", f"Client is not authorized for grant_type '{grant_type}'"
            )
        issuer = provider.base_url(request)
        handlers = {
            AUTHORIZATION_CODE: authorization_code,
            REFRESH_TOKEN: refresh_token,
            CLIENT_CREDENTIALS: client_credentials,
            TOKEN_EXCHANGE: token_exchange,
        }
        handler = handlers.get(grant_type)
        if handler is None:
            raise OAuthError("unsupported_grant_type", f"Unsupported grant_type: {grant_type}")
        return handler(provider, client, form, issuer)


def authorization_code(
    provider: FakeOIDCProvider, client: Client, form: dict[str, str], issuer: str
) -> JSONResponse:
    code_value, redirect_uri = form.get("code"), form.get("redirect_uri")
    if not code_value:
        raise OAuthError("invalid_request", "code is required")
    if not redirect_uri:
        raise OAuthError("invalid_request", "redirect_uri is required")

    code = provider.store.codes.get(code_value)
    if code is None or code.used or code.expires_at < provider.now():
        raise OAuthError("invalid_grant", "Invalid or expired authorization code")
    if code.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Authorization code was not issued to this client")
    if code.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "redirect_uri does not match")

    if code.code_challenge:
        verifier = form.get("code_verifier")
        if not verifier:
            raise OAuthError("invalid_request", "code_verifier is required")
        if not pkce.is_valid_verifier(verifier):
            raise OAuthError("invalid_request", "Invalid code_verifier format")
        method = code.code_challenge_method or "S256"
        if not pkce.verify(verifier, code.code_challenge, method):
            raise OAuthError("invalid_grant", "PKCE verification failed")

    code.used = True
    access = tokens.issue_access_token(
        provider, client, code.scopes, issuer, user_id=code.user_id, nonce=code.nonce
    )
    refresh = tokens.issue_refresh_token(provider, client, code.scopes, code.user_id)
    extra: dict[str, Any] = {"refresh_token": refresh}
    if "openid" in code.scopes:
        extra["id_token"] = tokens.issue_id_token(
            provider,
            client,
            code.user_id,
            issuer,
            nonce=code.nonce,
            auth_time=code.auth_time,
            access_token=access,
        )
    return _response(access, tokens.access_token_ttl(provider, client), code.scopes, **extra)


def refresh_token(
    provider: FakeOIDCProvider, client: Client, form: dict[str, str], issuer: str
) -> JSONResponse:
    value = form.get("refresh_token")
    if not value:
        raise OAuthError("invalid_request", "refresh_token is required")
    record = provider.store.refresh_tokens.get(value)
    if record is None or record.revoked or record.expires_at < provider.now():
        raise OAuthError("invalid_grant", "Invalid or expired refresh token")
    if record.client_id != client.client_id:
        raise OAuthError("invalid_grant", "Refresh token was not issued to this client")

    requested = form.get("scope", "").split()
    if requested and not set(requested) <= set(record.scopes):
        raise OAuthError("invalid_scope", "Requested scopes exceed original token scopes")
    scopes = requested or record.scopes

    record.revoked = True  # rotation: a refresh token is good for one use
    access = tokens.issue_access_token(provider, client, scopes, issuer, user_id=record.user_id)
    new_refresh = tokens.issue_refresh_token(provider, client, scopes, record.user_id)
    return _response(
        access, tokens.access_token_ttl(provider, client), scopes, refresh_token=new_refresh
    )


def client_credentials(
    provider: FakeOIDCProvider, client: Client, form: dict[str, str], issuer: str
) -> JSONResponse:
    if not client.is_confidential:
        raise OAuthError(
            "unauthorized_client", "client_credentials grant requires a confidential client"
        )
    scopes = form.get("scope", "").split() or list(client.allowed_scopes)
    if not all(client_scope_matches(scope, client.allowed_scopes) for scope in scopes):
        raise OAuthError("invalid_scope", "Requested scope exceeds client's allowed scopes")
    access = tokens.issue_access_token(provider, client, scopes, issuer)
    return _response(access, tokens.access_token_ttl(provider, client), scopes)


def _decode_unverified(token: str, what: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.DecodeError as exc:
        raise OAuthError("invalid_request", f"Failed to decode {what}: {exc}") from exc


def _validate_subject_token(
    provider: FakeOIDCProvider, token: str, token_type: str
) -> tuple[str | None, list[str]]:
    """The ``(user_id, scopes)`` of a subject token."""
    if token_type not in SUBJECT_TOKEN_TYPES:
        raise OAuthError("invalid_request", f"Unsupported subject_token_type: {token_type}")
    claims = _decode_unverified(token, "subject token")
    if token_type == TOKEN_TYPE_ACCESS_TOKEN:
        jti = claims.get("jti")
        if not jti:
            raise OAuthError("invalid_request", "Subject token missing jti claim")
        record = provider.store.access_tokens.get(jti)
        if record is None or record.revoked:
            raise OAuthError("invalid_request", "Subject token not found or revoked")
        if record.expires_at < provider.now():
            raise OAuthError("invalid_request", "Subject token has expired")
        return record.user_id, record.scopes
    user_id = None
    with contextlib.suppress(ValueError):
        user_id = str(uuid.UUID(claims.get("sub", "")))
    return user_id, claims.get("scope", "").split()


def token_exchange(
    provider: FakeOIDCProvider, client: Client, form: dict[str, str], issuer: str
) -> JSONResponse:
    subject_token = form.get("subject_token")
    subject_token_type = form.get("subject_token_type")
    if not subject_token:
        raise OAuthError("invalid_request", "subject_token is required")
    if not subject_token_type:
        raise OAuthError("invalid_request", "subject_token_type is required")
    if not client.is_confidential:
        raise OAuthError(
            "unauthorized_client", "token-exchange grant requires a confidential client"
        )

    user_id, subject_scopes = _validate_subject_token(provider, subject_token, subject_token_type)

    actor = None
    if form.get("actor_token"):
        if not form.get("actor_token_type"):
            raise OAuthError(
                "invalid_request", "actor_token_type is required when actor_token is provided"
            )
        claims = _decode_unverified(form["actor_token"], "actor token")
        actor = {
            "sub": claims.get("sub"),
            "client_id": claims.get("client_id") or claims.get("azp"),
        }

    scopes = _exchange_scopes(provider, client, form.get("scope"), subject_scopes, user_id)
    access = tokens.issue_access_token(
        provider,
        client,
        scopes,
        issuer,
        user_id=user_id,
        audience=form.get("audience") or form.get("resource"),
        actor=actor,
    )
    return _response(access, tokens.access_token_ttl(provider, client), scopes)


def _exchange_scopes(
    provider: FakeOIDCProvider,
    client: Client,
    requested_scope: str | None,
    subject_scopes: list[str],
    user_id: str | None,
) -> list[str]:
    """Requested scopes, kept when the client may ask for them and the user holds them."""
    requested = requested_scope.split() if requested_scope else subject_scopes
    allowed = [s for s in requested if exchange_scope_matches(s, client.allowed_scopes)]
    if not allowed and requested:
        raise OAuthError("invalid_scope", "Requested scopes not allowed for this client")

    if user_id is None:
        granted = [s for s in allowed if s in subject_scopes]
        if not granted and allowed:
            raise OAuthError("invalid_scope", "Cannot escalate scopes without user identity")
        return granted

    user = provider.users.get(user_id)
    held = user.scopes if user else ()
    granted = [s for s in allowed if s in subject_scopes or user_has_scope(held, s)]
    denied = [s for s in allowed if s not in granted]
    if not granted and allowed:
        raise OAuthError(
            "insufficient_scope",
            f"User does not have permission for requested scopes: {', '.join(denied)}",
        )
    return granted
