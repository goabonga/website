# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OIDC Discovery endpoint."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.schemas.discovery import OpenIDConfigurationResponse
from auth.services.issuer import get_issuer_from_context

router = APIRouter()


@router.get(
    "/.well-known/openid-configuration",
    response_model=OpenIDConfigurationResponse,
)
async def openid_configuration(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> OpenIDConfigurationResponse:
    """Return the OpenID Connect Discovery metadata document.

    Relying parties (clients) fetch this document once at startup to bootstrap
    their configuration: they learn the issuer's endpoint URLs
    (`authorization_endpoint`, `token_endpoint`, `jwks_uri`,
    `userinfo_endpoint`, etc.), the supported grant types, scopes, response
    types, PKCE code-challenge methods, and ID token signing algorithms.
    Clients SHOULD cache the response according to HTTP cache headers and only
    re-fetch when the cache expires or a key-rollover is detected.  This
    document is also compatible with RFC 8414 OAuth 2.0 Authorization Server
    Metadata: both specifications share the same JSON fields; the
    `/.well-known/openid-configuration` path is the OIDC Discovery entry point
    while RFC 8414 additionally defines `/.well-known/oauth-authorization-server`.

    **Specification:**
    - OpenID Connect Discovery 1.0 §3 (Provider Metadata) and §4 (Obtaining Metadata)
    - RFC 8414 §2 (Authorization Server Metadata) and §3 (Obtaining Metadata)

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl https://auth.example.com/.well-known/openid-configuration
    ```
    """
    # Get issuer from tenant context (secure - derived from DB config, not Host header)
    issuer = await get_issuer_from_context(db)

    return OpenIDConfigurationResponse(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/oauth2/authorize",
        token_endpoint=f"{issuer}/oauth2/token",
        userinfo_endpoint=f"{issuer}/userinfo",
        jwks_uri=f"{issuer}/.well-known/jwks.json",
        revocation_endpoint=f"{issuer}/oauth2/revoke",
        introspection_endpoint=f"{issuer}/oauth2/introspect",
        device_authorization_endpoint=f"{issuer}/oauth2/device",
        pushed_authorization_request_endpoint=f"{issuer}/oauth2/par",
        registration_endpoint=f"{issuer}/auth/register",
        scopes_supported=[
            "openid",
            "profile",
            "email",
            "offline_access",
        ],
        response_types_supported=[
            "code",
            "token",
            "id_token",
            "code token",
            "code id_token",
            "token id_token",
            "code token id_token",
        ],
        response_modes_supported=[
            "query",
            "fragment",
            "form_post",
        ],
        grant_types_supported=[
            "authorization_code",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:device_code",
            "urn:ietf:params:oauth:grant-type:token-exchange",
        ],
        subject_types_supported=["pairwise"],
        id_token_signing_alg_values_supported=["RS256"],
        token_endpoint_auth_methods_supported=[
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        code_challenge_methods_supported=["S256", "plain"],
        claims_supported=[
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
        request_parameter_supported=True,
        request_uri_parameter_supported=True,
        require_request_uri_registration=True,
    )
