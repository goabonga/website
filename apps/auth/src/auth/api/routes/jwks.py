# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""JWKS (JSON Web Key Set) endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_jwks_service
from auth.api.schemas.jwks import JWKSResponse, PublicJWK
from auth.services.jwks import JWKSService

router = APIRouter()


@router.get("/.well-known/jwks.json", response_model=JWKSResponse)
async def jwks(
    db: AsyncSession = Depends(get_db),
    jwks_service: JWKSService = Depends(get_jwks_service),
) -> JWKSResponse:
    """Return the authorization server's public JSON Web Key Set.

    Publishes all active (non-revoked) public signing keys so that relying
    parties can verify the signatures of ID tokens and JWT access tokens issued
    by this server. Only public key material is exposed — RSA keys include
    ``kty``, ``kid``, ``use``, ``alg``, ``n``, and ``e``; EC keys include
    ``kty``, ``kid``, ``use``, ``crv``, ``x``, and ``y``. The corresponding
    private key is never included in the response. Clients should cache this
    response (respecting ``Cache-Control``) and refresh it only when they
    encounter a ``kid`` in a token header that is not present in their cached
    set, to accommodate seamless key rotation. During a rotation grace period
    the endpoint may also include recently superseded keys so that tokens
    signed with the old key remain verifiable until they expire.

    **Specification:**
    - RFC 7517 §5 — JSON Web Key Set (JWKS) format
    - RFC 7518 — JSON Web Algorithms (`kty`, `alg`, `use`, `kid` values)
    - OpenID Connect Discovery 1.0 §3 — `jwks_uri` metadata field

    **Authentication:** none (public endpoint)

    **Example:**
    ```
    curl https://auth.example.com/.well-known/jwks.json | jq '.keys[0].kid'
    ```
    """
    keys = await jwks_service.get_all_public_keys(db)

    return JWKSResponse(
        keys=[PublicJWK(**jwks_service.to_jwk_public(key)) for key in keys],
    )
