# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin routes for managing authorized clients."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from custom_domain.auth import AuthContext, require_scopes
from custom_domain.config import settings
from custom_domain.database import get_db
from custom_domain.logging import get_logger
from custom_domain.models import AuthorizedClient, CustomDomain
from custom_domain.schemas import (
    ClientCreate,
    ClientListItem,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from custom_domain.services import template_service

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/clients", tags=["admin-clients"])

ADMIN_SCOPES = (settings.admin_scope, f"{settings.admin_scope}:clients")


async def ensure_template_usable(db: AsyncSession, template_id: int | None, client_id: str) -> None:
    """Refuse a default template that the client could not use itself.

    Raises:
        HTTPException: 400 when the template does not exist, is inactive or belongs
            to another client
    """
    if template_id is None:
        return
    if not await template_service.get_usable_template(db, template_id, client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nginx template not found or not available to this client",
        )


@router.get("", response_model=ClientListResponse)
async def list_clients(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """List all authorized clients."""
    result = await db.execute(select(AuthorizedClient).order_by(AuthorizedClient.name))
    clients = result.scalars().all()

    # Get domain counts
    items: list[ClientListItem] = []
    for client in clients:
        count_query = select(func.count()).where(CustomDomain.client_id == client.client_id)
        domains_count = await db.scalar(count_query) or 0

        item = ClientListItem(
            id=client.id,
            client_id=client.client_id,
            name=client.name,
            default_upstream_target=client.default_upstream_target or "",
            default_cname_target=client.default_cname_target or "",
            default_nginx_template_id=client.default_nginx_template_id,
            max_domains=client.max_domains,
            is_active=client.is_active,
            domains_count=domains_count,
            created_at=client.created_at,
        )
        items.append(item)

    return ClientListResponse(
        items=items,
        total=len(items),
    )


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Create a new authorized client."""
    # Check if client_id already exists
    existing = await db.execute(
        select(AuthorizedClient).where(AuthorizedClient.client_id == data.client_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client ID already exists",
        )

    await ensure_template_usable(db, data.default_nginx_template_id, data.client_id)

    client = AuthorizedClient(
        client_id=data.client_id,
        name=data.name,
        description=data.description,
        default_upstream_target=data.default_upstream_target,
        default_cname_target=data.default_cname_target,
        default_nginx_template_id=data.default_nginx_template_id,
        max_domains=data.max_domains,
        metadata_=data.metadata,
        is_active=True,
    )

    db.add(client)
    await db.commit()
    await db.refresh(client)

    logger.info("Client created: %s", client.client_id)

    return ClientResponse.model_validate(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Get client details."""
    result = await db.execute(select(AuthorizedClient).where(AuthorizedClient.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    return ClientResponse.model_validate(client)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: int,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Update a client."""
    result = await db.execute(select(AuthorizedClient).where(AuthorizedClient.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    await ensure_template_usable(db, update_data.get("default_nginx_template_id"), client.client_id)
    for field, value in update_data.items():
        if field == "metadata":
            client.metadata_ = value
        else:
            setattr(client, field, value)

    await db.commit()
    await db.refresh(client)

    logger.info("Client updated: %s", client.client_id)

    return ClientResponse.model_validate(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Delete a client."""
    result = await db.execute(select(AuthorizedClient).where(AuthorizedClient.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # Check for associated domains
    count_query = select(func.count()).where(CustomDomain.client_id == client.client_id)
    domains_count = await db.scalar(count_query) or 0

    if domains_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete client with {domains_count} associated domains",
        )

    await db.delete(client)
    await db.commit()

    logger.info("Client deleted: %s", client.client_id)


@router.post("/{client_id}/deactivate", response_model=ClientResponse)
async def deactivate_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Deactivate a client."""
    result = await db.execute(select(AuthorizedClient).where(AuthorizedClient.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    client.is_active = False
    await db.commit()
    await db.refresh(client)

    logger.info("Client deactivated: %s", client.client_id)

    return ClientResponse.model_validate(client)


@router.post("/{client_id}/activate", response_model=ClientResponse)
async def activate_client(
    client_id: int,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(*ADMIN_SCOPES)),
):
    """Activate a client."""
    result = await db.execute(select(AuthorizedClient).where(AuthorizedClient.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    client.is_active = True
    await db.commit()
    await db.refresh(client)

    logger.info("Client activated: %s", client.client_id)

    return ClientResponse.model_validate(client)
