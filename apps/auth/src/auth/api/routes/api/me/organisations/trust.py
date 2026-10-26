# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-scoped organisation trust API endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_trust_service
from auth.api.routes.api.deps import get_current_user_bearer, require_org_membership
from auth.api.schemas.api.organisations import (
    AddTrustedSourceRequest,
    TrustConfigResponse,
    TrustedSourceResponse,
    UpdateTrustModeRequest,
)
from auth.db.models.tenant import TenantTrustMode
from auth.db.models.user import User
from auth.services.trust import TrustPolicyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trust", tags=["me-organisations:trust"])


def _build_trust_config_response(config: dict) -> TrustConfigResponse:
    """Convert the raw trust config dict into a typed response."""
    sources = [
        TrustedSourceResponse(
            id=uuid.UUID(s["id"]),
            trusted_tenant_id=uuid.UUID(s["trusted_tenant_id"])
            if s.get("trusted_tenant_id")
            else None,
            trusted_tenant_name=s.get("trusted_tenant_name"),
            trusted_tenant_slug=s.get("trusted_tenant_slug"),
            is_platform=s.get("is_platform", False),
            description=s.get("description"),
        )
        for s in config.get("trusted_sources", [])
    ]
    return TrustConfigResponse(
        mode=config["trust_mode"],
        trusted_sources=sources,
    )


@router.get("/", response_model=TrustConfigResponse)
async def get_trust_config(
    org_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> TrustConfigResponse:
    """Retrieve the trust configuration for an organisation.

    Returns the current trust mode and the list of trusted source tenants.
    Trust configuration controls which external tenants may perform token
    exchange or federated login into this organisation.

    **Required scope:** org membership + `trust:read`

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/trust/
    ```
    """
    _user, _tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="trust:read",
    )

    config = await trust_service.get_tenant_trust_config(db, org_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    return _build_trust_config_response(config)


@router.put("/", response_model=TrustConfigResponse)
async def update_trust_mode(
    org_id: uuid.UUID,
    body: UpdateTrustModeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> TrustConfigResponse:
    """Update the trust mode for an organisation.

    Sets the strategy used to evaluate incoming token-exchange and federated
    login requests. Switching to a restrictive mode (e.g. `allowlist`) means
    only explicitly listed trusted sources will be accepted; switching to an
    open mode widens the accepted token issuers.

    **Required scope:** org membership + `trust:write`

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"mode": "allowlist"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/trust/
    ```
    """
    _user, _tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="trust:write",
    )

    # Validate mode value against enum
    try:
        trust_mode = TenantTrustMode(body.mode)
    except ValueError:
        valid = [m.value for m in TenantTrustMode]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trust mode: {body.mode}. Valid values: {valid}",
        )

    success = await trust_service.update_trust_mode(db, org_id, trust_mode)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    logger.info(
        "ACTION: me_trust_mode_update, user_id=%s, org_id=%s, mode=%s",
        user.id,
        org_id,
        trust_mode.value,
    )

    config = await trust_service.get_tenant_trust_config(db, org_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    return _build_trust_config_response(config)


@router.post(
    "/sources",
    response_model=TrustConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_trusted_source(
    org_id: uuid.UUID,
    body: AddTrustedSourceRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> TrustConfigResponse:
    """Add a trusted source tenant to an organisation.

    Registers a remote tenant as an allowed token-exchange or federation
    source for this organisation. Once added, users authenticated by the
    source tenant may request a cross-tenant access token without re-prompting
    for credentials. Returns `409` if the source tenant is already registered.

    **Required scope:** org membership + `trust:write`

    **Example:**
    ```
    curl -X POST \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"source_tenant_id": "a3bb189e-8bf9-3888-9912-ace4e6543002"}' \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/trust/sources
    ```
    """
    _user, _tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="trust:write",
    )

    source = await trust_service.add_trusted_source(
        db,
        org_id,
        body.source_tenant_id,
    )
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This tenant is already a trusted source",
        )

    logger.info(
        "ACTION: me_trusted_source_add, user_id=%s, org_id=%s, source_tenant_id=%s",
        user.id,
        org_id,
        body.source_tenant_id,
    )

    config = await trust_service.get_tenant_trust_config(db, org_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation not found",
        )

    return _build_trust_config_response(config)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_trusted_source(
    org_id: uuid.UUID,
    source_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_bearer)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> None:
    """Remove a trusted source tenant from an organisation.

    Revokes the cross-tenant trust relationship. Existing tokens issued via
    that federation path remain valid until they expire, but no new token
    exchanges from the removed source tenant will be accepted. Returns `404`
    if the source entry does not exist.

    **Required scope:** org membership + `trust:write`

    **Example:**
    ```
    curl -X DELETE \\
      -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/organisations/550e8400-e29b-41d4-a716-446655440000/trust/sources/a3bb189e-8bf9-3888-9912-ace4e6543002
    ```
    """
    _user, _tenant, _membership = await require_org_membership(
        org_id,
        request,
        db,
        user,
        required_scope="trust:write",
    )

    removed = await trust_service.remove_trusted_source(db, org_id, source_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted source not found",
        )

    logger.info(
        "ACTION: me_trusted_source_remove, user_id=%s, org_id=%s, source_id=%s",
        user.id,
        org_id,
        source_id,
    )
