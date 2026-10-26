# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token introspection (RFC 7662), revocation (RFC 7009) and the userinfo endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from e2e_support.oidc import tokens
from e2e_support.oidc.client_auth import authenticate
from e2e_support.oidc.errors import OAuthError
from e2e_support.oidc.http import read_form
from e2e_support.oidc.models import INTROSPECT_SCOPE

if TYPE_CHECKING:
    from e2e_support.oidc.provider import FakeOIDCProvider


def _unauthorized(detail: str, error: str = "invalid_token", status: int = 401) -> JSONResponse:
    """A userinfo failure: the auth application answers ``{"detail": "<message>"}``."""
    return JSONResponse(
        {"detail": detail},
        status_code=status,
        headers={"WWW-Authenticate": f'Bearer error="{error}"'},
    )


def install(provider: FakeOIDCProvider, app: FastAPI) -> None:
    """Add ``/oauth2/introspect``, ``/oauth2/revoke`` and ``/userinfo`` to ``app``."""

    def active_access_token(token: str) -> dict[str, Any] | None:
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.DecodeError:
            return None
        record = provider.store.access_tokens.get(claims.get("jti", ""))
        if record is None or record.revoked or record.expires_at < provider.now():
            return None
        return {
            "active": True,
            "scope": claims.get("scope"),
            "client_id": claims.get("client_id"),
            "token_type": "Bearer",
            "exp": claims.get("exp"),
            "iat": claims.get("iat"),
            "nbf": claims.get("nbf"),
            "sub": claims.get("sub"),
            "aud": claims.get("aud"),
            "iss": claims.get("iss"),
            "jti": claims.get("jti"),
        }

    def active_refresh_token(token: str) -> dict[str, Any] | None:
        record = provider.store.refresh_tokens.get(token)
        if record is None or record.revoked or record.expires_at < provider.now():
            return None
        client = provider.clients.get(record.client_id)
        return {
            "active": True,
            "scope": " ".join(record.scopes) or None,
            "client_id": record.client_id,
            "token_type": "refresh_token",
            "exp": int(record.expires_at),
            "sub": tokens.subject_for(provider, record.user_id, client) if client else None,
        }

    @app.post("/oauth2/introspect")
    async def introspect(request: Request) -> JSONResponse:
        form = await read_form(request)
        client = authenticate(provider, request.headers.get("authorization"), form)
        if INTROSPECT_SCOPE not in client.allowed_scopes:
            raise OAuthError(
                "insufficient_scope", "Client is not authorized to introspect tokens", 403
            )
        token = form.get("token", "")
        lookups = [active_access_token, active_refresh_token]
        if form.get("token_type_hint") == "refresh_token":
            lookups.reverse()
        for lookup in lookups:
            found = lookup(token)
            if found is not None:
                return JSONResponse({k: v for k, v in found.items() if v is not None})
        return JSONResponse({"active": False})

    @app.post("/oauth2/revoke")
    async def revoke(request: Request) -> Response:
        form = await read_form(request)
        authenticate(provider, request.headers.get("authorization"), form)
        token = form.get("token", "")
        try:
            jti = jwt.decode(token, options={"verify_signature": False}).get("jti", "")
        except jwt.DecodeError:
            jti = ""
        if access := provider.store.access_tokens.get(jti):
            access.revoked = True
        if refresh := provider.store.refresh_tokens.get(token):
            refresh.revoked = True
        return Response(status_code=200)  # RFC 7009: the same answer whether or not it existed

    async def userinfo(request: Request) -> JSONResponse:
        authorization = request.headers.get("authorization", "")
        access_token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        try:
            claims = jwt.decode(access_token, options={"verify_signature": False})
        except jwt.DecodeError:
            return _unauthorized("Invalid access token")
        jti = claims.get("jti")
        if not jti:
            return _unauthorized("Invalid access token")
        record = provider.store.access_tokens.get(jti)
        if record is None:
            return _unauthorized("Access token not found")
        if record.revoked:
            return _unauthorized("Access token has been revoked")
        if record.expires_at < provider.now():
            return _unauthorized("Access token has expired")
        scopes = claims.get("scope", "").split()
        if "openid" not in scopes:
            return _unauthorized(
                "Access token does not have openid scope", "insufficient_scope", 403
            )
        user = provider.users.get(record.user_id) if record.user_id else None
        if record.user_id is None:
            return _unauthorized("Access token has no associated user")
        if user is None:
            return _unauthorized("User not found or inactive")

        client = provider.clients[record.client_id]
        body: dict[str, Any] = {"sub": tokens.subject_for(provider, user.id, client)}
        if "profile" in scopes:
            if user.name:
                body["name"] = user.name
            if user.picture:
                body["picture"] = user.picture
        if "email" in scopes:
            body["email"] = user.email
            body["email_verified"] = user.email_verified
        return JSONResponse(body)

    app.add_api_route("/userinfo", userinfo, methods=["GET", "POST"])
