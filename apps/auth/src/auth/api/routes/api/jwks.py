# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin JWKS API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_jwks_service
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.jwks import (
    GenerateKeyRequest,
    JWKResponse,
    JWKRotateResponse,
    RotateKeysRequest,
)
from auth.db.models.user import User
from auth.services.jwks import JWKSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jwks", tags=["jwks"])


@router.get("/", response_model=list[JWKResponse])
async def list_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:read"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> list[JWKResponse]:
    """List all active JWK keys.

    Returns every non-revoked JSON Web Key known to the server, including
    their key ID (kid), algorithm, and activation status. Revoked keys are
    excluded from this listing.

    **Required scope:** `jwks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/jwks/
    ```
    """
    keys = await jwks_service.list(db, include_revoked=False)
    return [JWKResponse.model_validate(k) for k in keys]


@router.post("/", response_model=JWKResponse, status_code=status.HTTP_201_CREATED)
async def generate_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:write"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    body: GenerateKeyRequest | None = None,
) -> JWKResponse:
    """Generate a new JWK key pair.

    Creates a new RSA key pair and persists it. By default the new key is
    inactive and will not be used for token signing until explicitly activated
    via the activate endpoint or a rotation. Pass `activate=true` to mark the
    new key as active immediately (deactivating any previously active key).
    The RSA modulus size can be tuned via `key_size` (2048, 3072, or 4096).

    **Required scope:** `jwks:write`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"key_size": 4096, "activate": true}' \\
      https://auth.example.com/api/v1/jwks/
    ```

    **Responses:**
    - `201` — key created
    - `401` — missing or invalid bearer token
    - `403` — missing `jwks:write` scope
    - `422` — invalid `key_size` (must be 2048, 3072, or 4096)
    """
    params = body or GenerateKeyRequest()
    key_size = params.key_size if params.key_size is not None else 2048

    jwk = await jwks_service.generate_key(db, key_size=key_size, activate=params.activate)

    logger.info(
        "ACTION: jwk_generate_api_v1, admin_user_id=%s, kid=%s, key_size=%d, activate=%s",
        user.id,
        jwk.kid,
        key_size,
        params.activate,
    )

    return JWKResponse.model_validate(jwk)


@router.post("/rotate", response_model=JWKRotateResponse)
async def rotate_keys(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:rotate"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    body: RotateKeysRequest | None = None,
) -> JWKRotateResponse:
    """Rotate the active signing key.

    Generates a new JWK key pair and immediately activates it, deactivating
    the previously active key. The old key remains available for token
    verification until it is explicitly revoked or deleted. The RSA modulus
    size can be tuned via `key_size` (2048, 3072, or 4096); defaults to 2048.

    **Required scope:** `jwks:rotate`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"key_size": 4096}' \\
      https://auth.example.com/api/v1/jwks/rotate
    ```

    **Responses:**
    - `200` — key rotated
    - `401` — missing or invalid bearer token
    - `403` — missing `jwks:rotate` scope
    - `422` — invalid `key_size` (must be 2048, 3072, or 4096)
    """
    params = body or RotateKeysRequest()
    key_size = params.key_size if params.key_size is not None else 2048

    new_key = await jwks_service.rotate_keys(db, key_size=key_size)

    logger.info(
        "ACTION: jwk_rotate_api_v1, admin_user_id=%s, new_kid=%s, key_size=%d",
        user.id,
        new_key.kid,
        key_size,
    )

    return JWKRotateResponse(
        message="Keys rotated successfully",
        new_key=JWKResponse.model_validate(new_key),
    )


@router.get("/{kid}", response_model=JWKResponse)
async def get_key(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:read"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> JWKResponse:
    """Retrieve a single JWK key by key ID.

    Returns the full key record for the given `kid`, regardless of its
    activation or revocation status. Returns 404 if no key with that ID
    exists.

    **Required scope:** `jwks:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/jwks/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    jwk = await jwks_service.get_by_kid(db, kid)

    if not jwk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )

    return JWKResponse.model_validate(jwk)


@router.post("/{kid}/activate", response_model=JWKResponse)
async def activate_key(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:write"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> JWKResponse:
    """Activate a specific JWK key for token signing.

    Marks the given key as the active signing key and deactivates all other
    keys. Subsequent JWT issuance will use this key. Returns 400 if the key
    is in a state that prevents activation (e.g., already revoked).

    **Required scope:** `jwks:write`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/jwks/550e8400-e29b-41d4-a716-446655440000/activate
    ```
    """
    try:
        jwk = await jwks_service.activate_key(db, kid)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not jwk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )

    logger.info(
        "ACTION: jwk_activate_api_v1, admin_user_id=%s, kid=%s",
        user.id,
        kid,
    )

    return JWKResponse.model_validate(jwk)


@router.post("/{kid}/revoke", response_model=JWKResponse)
async def revoke_key(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:revoke"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> JWKResponse:
    """Revoke a JWK key.

    Marks the key as revoked so it can no longer be used for token signing or
    verification. Revoked keys are excluded from the public JWKS endpoint.
    The key record is retained in the database and can be permanently removed
    with the delete endpoint.

    **Required scope:** `jwks:revoke`

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/jwks/550e8400-e29b-41d4-a716-446655440000/revoke
    ```
    """
    jwk = await jwks_service.revoke_key(db, kid)

    if not jwk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )

    logger.info(
        "ACTION: jwk_revoke_api_v1, admin_user_id=%s, kid=%s",
        user.id,
        kid,
    )

    return JWKResponse.model_validate(jwk)


@router.delete("/{kid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("jwks:delete"))],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> Response:
    """Permanently delete a revoked JWK key.

    Removes the key record from the database. Only keys that have already been
    revoked can be deleted; attempting to delete an active or inactive key
    returns 404. This action is irreversible.

    **Required scope:** `jwks:delete`

    **Example:**
    ```
    curl -X DELETE -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/jwks/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    deleted = await jwks_service.delete(db, kid)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found or not revoked",
        )

    logger.info(
        "ACTION: jwk_delete_api_v1, admin_user_id=%s, kid=%s",
        user.id,
        kid,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
