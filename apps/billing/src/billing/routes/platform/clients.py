# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Bindings between OAuth clients and SaaS applications (admin scope)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext
from billing.database import get_db
from billing.models import SaasApp, SaasClientBinding
from billing.partition import require_admin
from billing.schemas.client_binding import ClientBindingResponse, ClientSaasResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform", tags=["Platform - Client bindings"])

ClientId = Annotated[str, Path(min_length=1, max_length=255, pattern=r"^\S+$")]


async def _get_saas_or_404(saas_id: str, db: AsyncSession) -> SaasApp:
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )
    return saas_app


@router.get("/saas/{saas_id}/clients", response_model=list[ClientBindingResponse])
async def list_saas_clients(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SaasClientBinding]:
    """List the OAuth clients bound to a SaaS application."""
    await _get_saas_or_404(saas_id, db)
    result = await db.execute(
        select(SaasClientBinding)
        .where(SaasClientBinding.saas_app_id == saas_id)
        .order_by(SaasClientBinding.created_at, SaasClientBinding.client_id)
    )
    return list(result.scalars().all())


@router.put("/saas/{saas_id}/clients/{client_id}", response_model=ClientBindingResponse)
async def bind_client(
    saas_id: str,
    client_id: ClientId,
    response: Response,
    _auth: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaasClientBinding:
    """Bind an OAuth client to a SaaS application (idempotent).

    Answers ``201`` when the binding is created and ``200`` when it existed.
    """
    saas_app = await _get_saas_or_404(saas_id, db)
    result = await db.execute(
        select(SaasClientBinding).where(
            SaasClientBinding.saas_app_id == saas_id,
            SaasClientBinding.client_id == client_id,
        )
    )
    binding = result.scalar_one_or_none()
    if binding:
        return binding

    binding = SaasClientBinding(saas_app_id=saas_id, client_id=client_id)
    db.add(binding)
    await db.flush()
    await db.refresh(binding)
    response.status_code = status.HTTP_201_CREATED
    logger.info(f"Bound client {client_id} to SaaS {saas_app.slug}")
    return binding


@router.delete("/saas/{saas_id}/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_client(
    saas_id: str,
    client_id: ClientId,
    _auth: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove the binding of an OAuth client to a SaaS application."""
    result = await db.execute(
        select(SaasClientBinding).where(
            SaasClientBinding.saas_app_id == saas_id,
            SaasClientBinding.client_id == client_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Binding not found",
        )
    await db.delete(binding)
    await db.flush()
    logger.info(f"Unbound client {client_id} from SaaS {saas_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/clients/{client_id}/saas", response_model=ClientSaasResponse)
async def list_client_saas(
    client_id: ClientId,
    _auth: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ClientSaasResponse:
    """List the SaaS applications an OAuth client is bound to."""
    result = await db.execute(
        select(SaasClientBinding.saas_app_id)
        .where(SaasClientBinding.client_id == client_id)
        .order_by(SaasClientBinding.saas_app_id)
    )
    return ClientSaasResponse(
        client_id=client_id, saas_ids=[str(saas_id) for saas_id in result.scalars().all()]
    )
