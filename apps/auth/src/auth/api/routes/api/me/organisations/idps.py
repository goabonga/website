# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped /me/organisations/{org_id}/idps endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.common import PaginatedResponse
from auth.api.schemas.api.organisations import (
    CreateIdPRequest,
    IdPResponse,
    UpdateIdPRequest,
)
from auth.core.encryption import encrypt_value
from auth.db.models.tenant import IdentityProvider, IdentityProviderType
from auth.db.models.user import User
from auth.services.tenant import tenant_service as _tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/idps", tags=["me-organisation-idps"])

_VALID_PROVIDER_TYPES = {e.value for e in IdentityProviderType}


def _idp_to_response(idp: IdentityProvider) -> IdPResponse:
    """Build an IdPResponse from an IdentityProvider model."""
    return IdPResponse(
        id=idp.id,
        name=idp.name,
        provider_type=idp.provider_type.value
        if hasattr(idp.provider_type, "value")
        else idp.provider_type,
        discovery_url=idp.discovery_url,
        authorization_endpoint=idp.authorization_endpoint,
        token_endpoint=idp.token_endpoint,
        userinfo_endpoint=idp.userinfo_endpoint,
        jwks_uri=idp.jwks_uri,
        client_id=idp.client_id,
        scopes=idp.scopes or [],
        attribute_mapping=idp.attribute_mapping,
        allowed_domains=idp.allowed_domains,
        is_active=idp.is_active,
        is_default=idp.is_default,
        auto_provision=idp.auto_provision,
        allow_linking=idp.allow_linking,
        icon_url=idp.icon_url,
        button_text=idp.button_text,
        display_order=idp.display_order,
        created_at=idp.created_at,
        updated_at=idp.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[IdPResponse])
async def list_my_org_idps(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[IdPResponse]:
    """List identity providers configured for an organisation.

    Returns a paginated list of all IdPs associated with the organisation.
    The `client_secret` field is never included in responses; it is write-only
    and stored encrypted.

    **Required scope:** org membership + `idp:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/idps/?page=1&page_size=20"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="idp:read")

    total = await _tenant_service.count_idps(db, org_id)
    idps = await _tenant_service.list_idps(db, org_id, page=page, page_size=page_size)

    items = [_idp_to_response(idp) for idp in idps]

    return PaginatedResponse[IdPResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/",
    response_model=IdPResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_org_idp(
    org_id: uuid.UUID,
    body: CreateIdPRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> IdPResponse:
    """Create a new identity provider for the organisation.

    Registers an OIDC or SAML IdP on the organisation. If `client_secret` is
    provided it is encrypted at rest and never returned in subsequent reads.
    Use `discovery_url` for OIDC providers that publish a well-known metadata
    document; supply individual endpoint fields for providers that do not.

    **Required scope:** org membership + `idp:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"name": "Corporate SSO", "provider_type": "oidc", "discovery_url": "https://sso.example.com/.well-known/openid-configuration", "client_id": "my-client", "client_secret": "s3cr3t", "scopes": ["openid", "email", "profile"]}' \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/idps/"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="idp:write")

    if body.provider_type not in _VALID_PROVIDER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid provider_type. Must be one of: {', '.join(sorted(_VALID_PROVIDER_TYPES))}"
            ),
        )

    client_secret_encrypted: bytes | None = None
    if body.client_secret:
        client_secret_encrypted = encrypt_value(body.client_secret)

    idp = IdentityProvider(
        tenant_id=org_id,
        name=body.name,
        provider_type=IdentityProviderType(body.provider_type),
        discovery_url=body.discovery_url,
        authorization_endpoint=body.authorization_endpoint,
        token_endpoint=body.token_endpoint,
        userinfo_endpoint=body.userinfo_endpoint,
        jwks_uri=body.jwks_uri,
        client_id=body.client_id,
        client_secret_encrypted=client_secret_encrypted,
        scopes=body.scopes,
        attribute_mapping=body.attribute_mapping,
        allowed_domains=body.allowed_domains,
        is_active=body.is_active,
        is_default=body.is_default,
        auto_provision=body.auto_provision,
        allow_linking=body.allow_linking,
        icon_url=body.icon_url,
        button_text=body.button_text,
        display_order=body.display_order,
    )
    await _tenant_service.add_idp(db, idp)

    logger.info(
        "ACTION: me_org_idp_create, user_id=%s, org_id=%s, idp_id=%s, type=%s",
        user.id,
        org_id,
        idp.id,
        idp.provider_type,
    )

    return _idp_to_response(idp)


@router.patch("/{idp_id}", response_model=IdPResponse)
async def update_my_org_idp(
    org_id: uuid.UUID,
    idp_id: uuid.UUID,
    body: UpdateIdPRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> IdPResponse:
    """Partially update an identity provider for the organisation.

    Accepts a sparse body — only fields present in the request are updated.
    Supplying `client_secret` re-encrypts and replaces the stored secret;
    omitting it leaves the existing secret unchanged.

    **Required scope:** org membership + `idp:write`

    **Example:**
    ```
    curl -X PATCH \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"is_active": true, "button_text": "Sign in with SSO"}' \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/idps/6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="idp:write")

    idp = await _tenant_service.get_idp(db, idp_id)
    if not idp or idp.tenant_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Identity provider not found"
        )

    update_data = body.model_dump(exclude_unset=True)

    # Handle client_secret specially -- encrypt before storing
    client_secret = update_data.pop("client_secret", None)
    if client_secret is not None:
        idp.client_secret_encrypted = encrypt_value(client_secret) if client_secret else None

    for field, value in update_data.items():
        setattr(idp, field, value)

    await db.flush()

    logger.info(
        "ACTION: me_org_idp_update, user_id=%s, org_id=%s, idp_id=%s",
        user.id,
        org_id,
        idp.id,
    )

    return _idp_to_response(idp)


@router.delete("/{idp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_org_idp(
    org_id: uuid.UUID,
    idp_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> None:
    """Delete an identity provider from the organisation.

    Permanently removes the IdP configuration, including its encrypted
    client secret. Any active federation sessions using this IdP are not
    terminated, but new logins via this provider will no longer be possible.

    **Required scope:** org membership + `idp:delete`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      "https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/idps/6ba7b810-9dad-11d1-80b4-00c04fd430c8"
    ```
    """
    await require_org_membership(org_id, request, db, user, required_scope="idp:delete")

    idp = await _tenant_service.get_idp(db, idp_id)
    if not idp or idp.tenant_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Identity provider not found"
        )

    await _tenant_service.delete_idp(db, idp)

    logger.info(
        "ACTION: me_org_idp_delete, user_id=%s, org_id=%s, idp_id=%s",
        user.id,
        org_id,
        idp.id,
    )
