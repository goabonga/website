# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/clients endpoints."""

import logging
import uuid
from typing import Annotated

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
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

router = APIRouter(prefix="/clients", tags=["me-organisation-clients"])

_hasher = PasswordHasher()
_client_service = OAuth2ClientService()


def _client_to_response(client: OAuth2Client) -> ClientResponse:
    """Build a ClientResponse from an OAuth2Client model."""
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
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


async def _get_my_org_client_or_404(
    db: AsyncSession,
    client_uuid: uuid.UUID,
    org_id: uuid.UUID,
) -> OAuth2Client:
    """Fetch a client via the service and verify it belongs to ``org_id``."""
    client = await _client_service.get_by_id(db, client_uuid)
    if not client or client.tenant_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.get("/", response_model=PaginatedResponse[ClientResponse])
async def list_my_org_clients(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ClientResponse]:
    """List OAuth2 clients belonging to an organisation.

    Returns a paginated list of all OAuth2 clients registered under the given
    organisation. Results are ordered by creation date descending.

    **Required scope:** org membership + `clients:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/?page=1&page_size=20"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:read")

    clients, total = await _client_service.list(
        db,
        page=page,
        page_size=page_size,
        tenant_id=org_id,
    )

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
async def create_my_org_client(
    org_id: uuid.UUID,
    body: CreateClientRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ClientCreatedResponse:
    """Create a new OAuth2 client for the organisation.

    Registers a new OAuth2 client scoped to the given organisation. If
    `is_confidential` is true, a client secret is generated and returned
    **once** in the response field `client_secret` — it is never retrievable
    again. Public clients receive no secret.

    **Required scope:** org membership + `clients:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "My App", "is_confidential": true, "redirect_uris": ["https://myapp.example.com/callback"], "allowed_grant_types": ["authorization_code"], "allowed_scopes": ["openid", "profile"]}' \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:write")

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
        tenant_id=org_id,
    )
    await _client_service.add(db, client)

    logger.info(
        "ACTION: me_org_client_create, user_id=%s, org_id=%s, client_id=%s",
        user.id,
        org_id,
        client.client_id,
    )

    # Include the plain-text secret only on creation
    return ClientCreatedResponse(
        **_client_to_response(client).model_dump(),
        client_secret=client_secret,
    )


@router.get("/{client_uuid}", response_model=ClientResponse)
async def get_my_org_client(
    org_id: uuid.UUID,
    client_uuid: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ClientResponse:
    """Get a single OAuth2 client by UUID.

    Returns the full configuration of an OAuth2 client belonging to the
    organisation. The client secret hash is never exposed.

    **Required scope:** org membership + `clients:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:read")
    client = await _get_my_org_client_or_404(db, client_uuid, org_id)
    return _client_to_response(client)


@router.patch("/{client_uuid}", response_model=ClientResponse)
async def update_my_org_client(
    org_id: uuid.UUID,
    client_uuid: uuid.UUID,
    body: UpdateClientRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ClientResponse:
    """Partially update an OAuth2 client.

    Applies a partial update to the client identified by `client_uuid`. Only
    the fields provided in the request body are modified; omitted fields retain
    their current values. The client secret is not affected by this endpoint.

    **Required scope:** org membership + `clients:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "Renamed App", "redirect_uris": ["https://myapp.example.com/cb"]}' \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:write")
    client = await _get_my_org_client_or_404(db, client_uuid, org_id)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    await db.flush()

    logger.info(
        "ACTION: me_org_client_update, user_id=%s, org_id=%s, client_id=%s",
        user.id,
        org_id,
        client.client_id,
    )

    return _client_to_response(client)


@router.delete("/{client_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_org_client(
    org_id: uuid.UUID,
    client_uuid: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Delete an OAuth2 client.

    Permanently removes the OAuth2 client from the organisation. All associated
    tokens and sessions for this client will no longer be valid. This action
    cannot be undone.

    **Required scope:** org membership + `clients:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:delete")
    client = await _get_my_org_client_or_404(db, client_uuid, org_id)

    await _client_service.delete(db, client)

    logger.info(
        "ACTION: me_org_client_delete, user_id=%s, org_id=%s, client_id=%s",
        user.id,
        org_id,
        client.client_id,
    )


@router.post("/{client_uuid}/rotate-secret", response_model=ClientSecretResponse)
async def rotate_my_org_client_secret(
    org_id: uuid.UUID,
    client_uuid: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ClientSecretResponse:
    """Rotate the client secret for a confidential OAuth2 client.

    Generates a new cryptographic secret for the specified confidential client
    and invalidates the previous one immediately. The new secret is returned
    **once** in the response — it is never retrievable again. Calling this on
    a public (non-confidential) client returns `400`.

    **Required scope:** org membership + `clients:rotate`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/clients/6ba7b810-9dad-11d1-80b4-00c04fd430c8/rotate-secret"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="clients:rotate")
    client = await _get_my_org_client_or_404(db, client_uuid, org_id)

    if not client.is_confidential:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rotate secret for a public client",
        )

    new_secret = generate_client_secret()
    client.client_secret_hash = _hasher.hash(new_secret)
    await db.flush()

    logger.info(
        "ACTION: me_org_client_rotate_secret, user_id=%s, org_id=%s, client_id=%s",
        user.id,
        org_id,
        client.client_id,
    )

    return ClientSecretResponse(
        client_id=client.client_id,
        client_secret=new_secret,
    )
