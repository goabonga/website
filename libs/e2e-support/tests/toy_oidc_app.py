# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A toy FastAPI application that logs users in through OpenID Connect.

It does what the real applications do: redirect anonymous visitors to the provider with
PKCE, exchange the code, validate the token with the JWKS and introspection, read the
profile from userinfo, and ask a token exchange which scopes the user holds to decide what
the navigation shows. Its endpoints and cookies mirror ``internal`` and ``knowledge``.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from html import escape
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

ACCESS_TOKEN_COOKIE = "access_token"
EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"


@dataclass
class ToyConfig:
    """Settings of the toy application; filled in once both servers are running."""

    issuer: str = ""
    base_url: str = ""
    client_id: str = "toy-web"
    service_client_id: str = "toy-api"
    service_client_secret: str = "toy-api-secret"
    billing_scope: str = "billing:read"


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_app(config: ToyConfig) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    async def validate(token: str) -> dict:
        """Verify the signature with the JWKS, then ask the provider if it is still active."""
        async with httpx.AsyncClient() as client:
            jwks = (await client.get(f"{config.issuer}/.well-known/jwks.json")).json()
            kid = jwt.get_unverified_header(token)["kid"]
            jwk = next(key for key in jwks["keys"] if key["kid"] == kid)
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(jwk).key,
                algorithms=["RS256"],
                issuer=config.issuer,
                options={"verify_aud": False},
            )
            introspection = await client.post(
                f"{config.issuer}/oauth2/introspect",
                data={"token": token},
                auth=(config.service_client_id, config.service_client_secret),
            )
            if not introspection.json().get("active"):
                raise jwt.InvalidTokenError("token revoked")
            return claims

    async def can_see_billing(token: str) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.issuer}/oauth2/token",
                data={
                    "grant_type": EXCHANGE_GRANT,
                    "subject_token": token,
                    "subject_token_type": ACCESS_TOKEN_TYPE,
                    "scope": config.billing_scope,
                },
                auth=(config.service_client_id, config.service_client_secret),
            )
        return response.status_code == 200

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return (
            "<title>Home</title><nav><a href='/dashboard'>Dashboard</a></nav>"
            "<h1>Toy application</h1>"
        )

    @app.get("/auth/login")
    async def login() -> Response:
        state, verifier = secrets.token_urlsafe(16), secrets.token_urlsafe(48)
        query = urlencode(
            {
                "client_id": config.client_id,
                "response_type": "code",
                "redirect_uri": f"{config.base_url}/auth/callback",
                "scope": "openid profile email offline_access",
                "state": state,
                "code_challenge": pkce_challenge(verifier),
                "code_challenge_method": "S256",
            }
        )
        response = RedirectResponse(f"{config.issuer}/oauth2/authorize?{query}", status_code=302)
        response.set_cookie("oauth_state", state, httponly=True, samesite="lax")
        response.set_cookie("oauth_verifier", verifier, httponly=True, samesite="lax")
        return response

    @app.get("/auth/callback", response_model=None)
    async def callback(request: Request) -> Response:
        params = request.query_params
        if "error" in params:
            return HTMLResponse(f"<h1>Login failed</h1><p>{escape(params['error'])}</p>", 400)
        if params.get("state") != request.cookies.get("oauth_state"):
            return HTMLResponse("<h1>Login failed</h1><p>invalid state</p>", 400)
        async with httpx.AsyncClient() as client:
            token = await client.post(
                f"{config.issuer}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": params.get("code", ""),
                    "redirect_uri": f"{config.base_url}/auth/callback",
                    "client_id": config.client_id,
                    "code_verifier": request.cookies.get("oauth_verifier", ""),
                },
            )
        if token.status_code != 200:
            return HTMLResponse("<h1>Login failed</h1><p>token exchange failed</p>", 400)
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie(
            ACCESS_TOKEN_COOKIE, token.json()["access_token"], httponly=True, samesite="lax"
        )
        response.delete_cookie("oauth_state")
        response.delete_cookie("oauth_verifier")
        return response

    @app.get("/dashboard", response_model=None)
    async def dashboard(request: Request) -> Response:
        token = request.cookies.get(ACCESS_TOKEN_COOKIE)
        if not token:
            return RedirectResponse("/auth/login", status_code=302)
        try:
            await validate(token)
        except jwt.InvalidTokenError:
            response = RedirectResponse("/auth/login", status_code=302)
            response.delete_cookie(ACCESS_TOKEN_COOKIE)
            return response
        async with httpx.AsyncClient() as client:
            profile = (
                await client.get(
                    f"{config.issuer}/userinfo", headers={"Authorization": f"Bearer {token}"}
                )
            ).json()
        billing = "<a href='/billing'>Billing</a>" if await can_see_billing(token) else ""
        return HTMLResponse(
            "<title>Dashboard</title>"
            f"<nav><a href='/dashboard'>Dashboard</a> {billing}</nav>"
            f"<h1>Welcome {escape(profile.get('name', ''))}</h1>"
            f"<p id='email'>{escape(profile.get('email', ''))}</p>"
            "<a href='/auth/logout'>Sign out</a>"
        )

    @app.get("/auth/logout")
    async def logout() -> Response:
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(ACCESS_TOKEN_COOKIE)
        return response

    return app
