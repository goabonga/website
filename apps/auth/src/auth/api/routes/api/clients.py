# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API v1 /clients admin endpoints."""

import logging
import uuid
from typing import Annotated

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import require_admin_scope
from auth.api.schemas.api.clients import (
    ClientCreatedResponse,
    ClientResponse,
    ClientSecretResponse,
    CreateClientRequest,
    UpdateClientRequest,
)
from auth.api.schemas.api.common import PaginatedResponse
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.user import User
from auth.services.oauth2_client import (
    OAuth2ClientService,
    generate_client_id,
    generate_client_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["admin-clients"])

_hasher = PasswordHasher()
_client_service = OAuth2ClientService()


def _client_to_response(client: OAuth2Client) -> ClientResponse:
    """Build an ClientResponse from an OAuth2Client model."""
    return ClientResponse(
        id=client.id,
        client_id=client.client_id,
        name=client.name,
        description=client.description,
        homepage_url=client.homepage_url,
        redirect_uris=client.redirect_uris or [],
        allowed_scopes=client.allowed_scopes or [],
        allowed_grant_types=client.allowed_grant_types or [],
        token_endpoint_auth_method=client.token_endpoint_auth_method,
        is_confidential=client.is_confidential,
        is_active=client.is_active,
        require_pkce=client.require_pkce,
        require_consent=client.require_consent,
        jwks_uri=client.jwks_uri,
        allowed_origins=client.allowed_origins,
        access_token_expiry_seconds=client.access_token_expiry_seconds,
        refresh_token_expiry_seconds=client.refresh_token_expiry_seconds,
        tenant_id=client.tenant_id,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


async def _get_client_or_404(db: AsyncSession, client_id: uuid.UUID) -> OAuth2Client:
    """Fetch a client by UUID via the service, or raise 404."""
    client = await _client_service.get_by_id(db, client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


@router.get("/", response_model=PaginatedResponse[ClientResponse])
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ClientResponse]:
    """List all OAuth2 clients across all tenants.

    Returns a paginated list of every OAuth2 client registered in the system,
    ordered by creation date descending. Results are global (not scoped to any
    single tenant).

    **Required scope:** `clients:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/clients/?page=1&page_size=20"
    ```
    """
    clients, total = await _client_service.list(db, page=page, page_size=page_size)

    items = [_client_to_response(c) for c in clients]

    return PaginatedResponse[ClientResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/",
    response_model=ClientCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
async def create_client(
    body: CreateClientRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:write"))],
) -> ClientCreatedResponse:
    """Create a new OAuth2 client.

    Registers a new OAuth2 client application. If `is_confidential` is true, a
    client secret is generated and returned once in the response — it will not
    be retrievable again. Public clients receive no secret.

    **Required scope:** `clients:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "My App", "redirect_uris": ["https://myapp.example.com/callback"], "allowed_grant_types": ["authorization_code"], "is_confidential": true, "require_pkce": false, "require_consent": true}' \\
      https://auth.example.com/api/v1/clients/
    ```
    """
    new_client_id = generate_client_id()
    client_secret: str | None = None
    client_secret_hash: str | None = None

    if body.is_confidential:
        client_secret = generate_client_secret()
        client_secret_hash = _hasher.hash(client_secret)

    client = OAuth2Client(
        client_id=new_client_id,
        client_secret_hash=client_secret_hash,
        name=body.name,
        description=body.description,
        homepage_url=body.homepage_url,
        redirect_uris=body.redirect_uris,
        allowed_scopes=body.allowed_scopes,
        allowed_grant_types=body.allowed_grant_types,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
        is_confidential=body.is_confidential,
        is_active=True,
        require_pkce=body.require_pkce,
        require_consent=body.require_consent,
        jwks_uri=body.jwks_uri,
        allowed_origins=body.allowed_origins,
        access_token_expiry_seconds=body.access_token_expiry_seconds,
        refresh_token_expiry_seconds=body.refresh_token_expiry_seconds,
    )
    await _client_service.add(db, client)

    logger.info(
        "ACTION: admin_client_create, admin_id=%s, client_id=%s, name=%s",
        user.id,
        client.client_id,
        client.name,
    )

    # Include the plain-text secret only on creation
    return ClientCreatedResponse(
        **_client_to_response(client).model_dump(),
        client_secret=client_secret,
    )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:read"))],
) -> ClientResponse:
    """Get a single OAuth2 client by its internal UUID.

    Returns the full configuration of an OAuth2 client. The client secret hash
    is never exposed; use the rotate-secret endpoint to issue a new secret.

    **Required scope:** `clients:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/clients/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    client = await _get_client_or_404(db, client_id)
    return _client_to_response(client)


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    body: UpdateClientRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:write"))],
) -> ClientResponse:
    """Partially update an OAuth2 client's configuration.

    Only fields present in the request body are modified; omitted fields retain
    their current values. This endpoint cannot be used to rotate the client
    secret — use `POST /{client_id}/rotate-secret` instead.

    **Required scope:** `clients:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "Updated App Name", "is_active": false}' \\
      https://auth.example.com/api/v1/clients/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    client = await _get_client_or_404(db, client_id)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await db.flush()

    logger.info(
        "ACTION: admin_client_update, admin_id=%s, client_id=%s",
        user.id,
        client.client_id,
    )

    return _client_to_response(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:delete"))],
) -> None:
    """Permanently delete an OAuth2 client.

    Removes the client record from the database. All active tokens issued to
    this client will become invalid immediately. This action is irreversible.

    **Required scope:** `clients:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/clients/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    client = await _get_client_or_404(db, client_id)
    await _client_service.delete(db, client)

    logger.info(
        "ACTION: admin_client_delete, admin_id=%s, client_id=%s",
        user.id,
        client.client_id,
    )


@router.post("/{client_id}/rotate-secret", response_model=ClientSecretResponse)
async def rotate_client_secret(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_scope("clients:rotate"))],
) -> ClientSecretResponse:
    """Rotate the client secret for a confidential OAuth2 client.

    Generates a new random client secret, stores its hash, and returns the
    plain-text secret once in the response. The previous secret is invalidated
    immediately. Returns 400 if the client is public (non-confidential).

    **Required scope:** `clients:rotate`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/clients/550e8400-e29b-41d4-a716-446655440000/rotate-secret
    ```
    """
    client = await _get_client_or_404(db, client_id)

    if not client.is_confidential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate secret for a public client",
        )

    new_secret = generate_client_secret()
    client.client_secret_hash = _hasher.hash(new_secret)
    await db.flush()

    logger.info(
        "ACTION: admin_client_rotate_secret, admin_id=%s, client_id=%s",
        user.id,
        client.client_id,
    )

    return ClientSecretResponse(
        client_id=client.client_id,
        client_secret=new_secret,
    )
