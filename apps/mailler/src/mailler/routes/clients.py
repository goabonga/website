# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Administration of the authorized clients."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mailler.auth import AuthContext, require_scopes
from mailler.config import settings
from mailler.database import get_db
from mailler.logging import get_logger
from mailler.models.client import AuthorizedClient
from mailler.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from mailler.services import clients as client_service

logger = get_logger(__name__)

router = APIRouter(prefix="/clients", tags=["Clients"])


def _to_response(client: AuthorizedClient) -> ClientResponse:
    return ClientResponse.model_validate(client)


async def _get_or_404(db: AsyncSession, client_id: str) -> AuthorizedClient:
    client = await client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("", response_model=ClientListResponse)
async def list_clients(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(default=None, description="Filter by activation"),
    search: str | None = Query(default=None, description="Search in client id and name"),
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> ClientListResponse:
    """List the registered clients (administrators only)."""
    stmt = select(AuthorizedClient).order_by(AuthorizedClient.client_id.asc())
    count_stmt = select(func.count(AuthorizedClient.id))

    if is_active is not None:
        stmt = stmt.where(AuthorizedClient.is_active == is_active)
        count_stmt = count_stmt.where(AuthorizedClient.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        match = AuthorizedClient.client_id.ilike(pattern) | AuthorizedClient.name.ilike(pattern)
        stmt = stmt.where(match)
        count_stmt = count_stmt.where(match)

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = math.ceil(total / page_size) if total > 0 else 1

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    clients = (await db.execute(stmt)).scalars().all()

    return ClientListResponse(
        items=[_to_response(c) for c in clients],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=ClientResponse, status_code=201)
async def create_client(
    request: ClientCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> ClientResponse:
    """Register a client (administrators only)."""
    client = client_service.new_client(request)

    try:
        db.add(client)
        await db.commit()
        await db.refresh(client)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"Client '{request.client_id}' is already registered"
        )

    logger.info(
        "Client registered",
        extra={"client_id": client.client_id, "user_id": str(auth.user.id)},
    )
    return _to_response(client)


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> ClientResponse:
    """Read a registered client (administrators only)."""
    return _to_response(await _get_or_404(db, client_id))


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    request: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(require_scopes(settings.admin_scope)),
) -> ClientResponse:
    """Update a registered client (administrators only).

    Only the fields present in the body change; deactivating a client with
    ``is_active: false`` refuses it from then on (within ``CLIENT_CACHE_TTL``).
    """
    client = await _get_or_404(db, client_id)

    client_service.apply_update(client, request)

    await db.commit()
    await db.refresh(client)
    client_service.clear_cache()

    logger.info(
        "Client updated",
        extra={"client_id": client.client_id, "user_id": str(auth.user.id)},
    )
    return _to_response(client)
