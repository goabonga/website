# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The authorization endpoint, with its login and consent pages.

The checks, their order and their error codes follow ``/oauth2/authorize`` of the auth
application: problems that make the redirect URI untrustworthy are shown on an error page,
the others are returned to the application as ``error`` redirects.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from e2e_support.oidc import pages, pkce
from e2e_support.oidc.http import read_form, with_params
from e2e_support.oidc.models import Client, User, client_scope_matches
from e2e_support.oidc.store import AuthorizationCode, PendingAuthorization

if TYPE_CHECKING:
    from e2e_support.oidc.provider import FakeOIDCProvider

#: Name of the cookie remembering who is logged in at the provider (single sign-on).
SESSION_COOKIE = "e2e_oidc_session"

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def is_valid_redirect_uri(uri: str) -> bool:
    """Same format rule as the auth application: https, http on localhost, or a custom scheme."""
    parsed = urlparse(uri)
    if not parsed.scheme:
        return False
    if parsed.scheme in ("http", "https"):
        if not parsed.netloc:
            return False
        return parsed.scheme == "https" or parsed.hostname in _LOCAL_HOSTS
    return bool(parsed.netloc or parsed.path)


def redirect_uri_registered(client: Client, uri: str) -> bool:
    """Exact match, or a ``*`` pattern; a client with no registered URI accepts any."""
    if not client.redirect_uris:
        return True
    for registered in client.redirect_uris:
        pattern = ".*".join(re.escape(part) for part in registered.split("*"))
        if re.fullmatch(pattern, uri):
            return True
    return False


def install(provider: FakeOIDCProvider, app: FastAPI) -> None:
    """Add the authorization endpoint and its pages to ``app``."""

    def error_page(error: str, description: str) -> HTMLResponse:
        return HTMLResponse(pages.error_page(error, description), status_code=400)

    def error_redirect(redirect_uri: str, error: str, description: str, state: str | None):
        url = with_params(redirect_uri, error=error, error_description=description, state=state)
        return RedirectResponse(url, status_code=302)

    def finish(request_id: str, user: User) -> Response:
        """Ask for consent if required, else issue the code."""
        pending = provider.store.pending[request_id]
        pending.user_id = user.id
        if provider.require_consent:
            client = provider.clients[pending.client_id]
            return HTMLResponse(
                pages.consent_page(
                    request_id, client.client_id, user.name or user.email, pending.scopes
                )
            )
        return issue_code(request_id, user)

    def issue_code(request_id: str, user: User) -> Response:
        pending = provider.store.pending.pop(request_id)
        code = secrets.token_urlsafe(32)
        provider.store.codes[code] = AuthorizationCode(
            code=code,
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            user_id=user.id,
            scopes=pending.scopes,
            code_challenge=pending.code_challenge,
            code_challenge_method=pending.code_challenge_method,
            nonce=pending.nonce,
            auth_time=int(provider.now()),
            expires_at=provider.now() + provider.code_ttl,
        )
        url = with_params(pending.redirect_uri, code=code, state=pending.state)
        return RedirectResponse(url, status_code=302)

    def session_user(request: Request) -> User | None:
        user_id = provider.store.sessions.get(request.cookies.get(SESSION_COOKIE, ""))
        return provider.users.get(user_id) if user_id else None

    @app.get("/oauth2/authorize")
    async def authorize(request: Request) -> Response:
        q = request.query_params
        response_type, redirect_uri = q.get("response_type"), q.get("redirect_uri")
        state = q.get("state")

        if not response_type:
            return error_page("invalid_request", "response_type is required")
        if not redirect_uri:
            return error_page("invalid_request", "redirect_uri is required")
        if response_type != "code":
            return error_page("unsupported_response_type", "Only 'code' response type is supported")
        if not is_valid_redirect_uri(redirect_uri):
            return error_page("invalid_request", "Invalid redirect_uri")
        client = provider.clients.get(q.get("client_id", ""))
        if client is None or not client.is_active:
            return error_page("unauthorized_client", "Unknown or inactive client")
        if not redirect_uri_registered(client, redirect_uri):
            return error_page("invalid_request", "redirect_uri not registered for this client")

        scopes = q.get("scope", "").split() or ["openid"]
        if not all(client_scope_matches(scope, client.allowed_scopes) for scope in scopes):
            return error_redirect(
                redirect_uri, "invalid_scope", "One or more requested scopes are not allowed", state
            )

        challenge, method = q.get("code_challenge"), q.get("code_challenge_method")
        if client.require_pkce:
            if not challenge:
                return error_redirect(
                    redirect_uri,
                    "invalid_request",
                    "PKCE is required. Provide code_challenge.",
                    state,
                )
            method = method or "S256"
            if not pkce.is_valid_method(method):
                return error_redirect(
                    redirect_uri,
                    "invalid_request",
                    "Invalid code_challenge_method. Use S256.",
                    state,
                )
            if not pkce.is_valid_challenge(challenge):
                return error_redirect(
                    redirect_uri, "invalid_request", "Invalid code_challenge format", state
                )

        request_id = secrets.token_urlsafe(16)
        provider.store.pending[request_id] = PendingAuthorization(
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            state=state,
            code_challenge=challenge,
            code_challenge_method=method if challenge else None,
            nonce=q.get("nonce"),
            login_hint=q.get("login_hint"),
        )
        prompts = q.get("prompt", "").split()

        if provider.auto_approve:
            hinted = provider.user_by_email(q.get("login_hint", ""))
            user = hinted or next(iter(provider.users.values()), None)
            if user is None:
                return error_page("server_error", "auto_approve is on but no user is configured")
            return finish(request_id, user)

        user = None if "login" in prompts else session_user(request)
        if user is not None:
            return finish(request_id, user)
        if "none" in prompts:
            provider.store.pending.pop(request_id, None)
            return error_redirect(redirect_uri, "login_required", "Login is required", state)
        return HTMLResponse(pages.login_page(request_id, client.client_id, q.get("login_hint", "")))

    @app.post("/oauth2/authorize/login")
    async def login(request: Request) -> Response:
        form = await read_form(request)
        request_id = form.get("request_id", "")
        pending = provider.store.pending.get(request_id)
        if pending is None:
            return error_page("invalid_request", "Unknown or expired authorization request")
        user = provider.user_by_email(form.get("email", ""))
        if user is None or (user.password is not None and form.get("password") != user.password):
            page = pages.login_page(
                request_id,
                pending.client_id,
                form.get("email", ""),
                "Invalid email or password.",
            )
            return HTMLResponse(page)
        session_id = secrets.token_urlsafe(24)
        provider.store.sessions[session_id] = user.id
        response = finish(request_id, user)
        if response.status_code in (301, 302):
            response.status_code = 303
        response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax", path="/")
        return response

    @app.post("/oauth2/authorize/consent")
    async def consent(request: Request) -> Response:
        form = await read_form(request)
        request_id = form.get("request_id", "")
        pending = provider.store.pending.get(request_id)
        user = provider.users.get(pending.user_id) if pending and pending.user_id else None
        if pending is None or user is None:
            return error_page("invalid_request", "Unknown or expired authorization request")
        if form.get("decision") != "allow":
            provider.store.pending.pop(request_id)
            return error_redirect(
                pending.redirect_uri, "access_denied", "The user denied the request", pending.state
            )
        response = issue_code(request_id, user)
        response.status_code = 303
        return response
