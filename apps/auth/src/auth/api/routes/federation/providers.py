# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Federation provider listing and authorization initiation."""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db
from auth.api.schemas.federation.providers import (
    IdentityProviderResponse,
    ProvidersListResponse,
)
from auth.middlewares.tenant import get_tenant_context
from auth.services.federation import FederationService, federation_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers", response_model=ProvidersListResponse)
async def list_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_slug: str | None = Query(None, description="Tenant slug (optional if using subdomain)"),
) -> ProvidersListResponse:
    """List available identity providers for a tenant.

    This endpoint returns all active identity providers configured for the tenant,
    which can be used to render the login page with social/SSO buttons.
    """
    # Get tenant from context or query param
    tenant_context = get_tenant_context()
    resolved_slug = tenant_slug or (tenant_context.tenant_slug if tenant_context else None)

    if not resolved_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant not specified. Use subdomain, path prefix, or tenant_slug parameter.",
        )

    providers = await federation_service.get_tenant_identity_providers(db, resolved_slug)

    return ProvidersListResponse(
        tenant_slug=resolved_slug,
        providers=[
            IdentityProviderResponse(
                id=str(idp.id),
                name=idp.name,
                provider_type=idp.provider_type.value,
                icon_url=idp.icon_url,
                button_text=idp.button_text or f"Continue with {idp.name}",
            )
            for idp in providers
        ],
        local_login_enabled=True,  # TODO: Make configurable per tenant
    )


@router.get("/{idp_id}/authorize")
async def initiate_federation(
    request: Request,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    redirect_uri: str | None = Query(None, description="Where to redirect after authentication"),
    state: str | None = Query(None, description="State to preserve through the flow"),
) -> RedirectResponse:
    """Initiate federation flow with an external identity provider.

    This endpoint redirects the user to the external IdP for authentication.
    After successful authentication, the IdP will redirect back to our callback endpoint.
    """
    # Get tenant context
    tenant_context = get_tenant_context()
    if not tenant_context or not tenant_context.tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required for federation",
        )

    # Get IdP configuration
    idp = await federation_service.get_identity_provider(db, idp_id)
    if not idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    if not idp.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity provider is not active",
        )

    # Generate security parameters
    nonce = FederationService.generate_nonce()
    code_verifier = FederationService.generate_code_verifier()
    internal_state = FederationService.generate_state()

    # Build callback URL
    # Use the request's base URL to construct callback
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    callback_url = f"{scheme}://{host}/federation/callback"

    # Store state in session for validation on callback
    # We encode all necessary info in the state parameter
    state_data = {
        "tenant_slug": tenant_context.tenant_slug,
        "idp_id": str(idp.id),
        "nonce": nonce,
        "code_verifier": code_verifier,
        "original_state": state,
        "redirect_uri": redirect_uri,
        "internal_state": internal_state,
    }

    # For now, encode state in URL (should use server-side session/cache in production)
    import base64

    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    # Get authorization URL
    auth_url = await federation_service.get_authorization_url(
        idp=idp,
        callback_url=callback_url,
        state=encoded_state,
        nonce=nonce,
        code_verifier=code_verifier,
    )

    logger.info(
        "Initiating federation: tenant=%s, idp=%s, callback=%s",
        tenant_context.tenant_slug,
        idp.name,
        callback_url,
    )

    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
