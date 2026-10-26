# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Customer management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext, require_scopes
from billing.config import settings
from billing.database import get_db
from billing.models import Customer, SaasApp
from billing.schemas import CustomerCreate, CustomerResponse, CustomerUpdate
from billing.schemas.customer import CustomerPortalResponse
from billing.services import get_stripe_service
from billing.services.redirects import RedirectNotAllowed, ensure_allowed_redirect

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform/{saas_id}/customers", tags=["Platform - Customers"])


async def get_saas_app_or_404(saas_id: str, db: AsyncSession) -> SaasApp:
    """Get SaaS app or raise 404."""
    result = await db.execute(select(SaasApp).where(SaasApp.id == saas_id))
    saas_app = result.scalar_one_or_none()
    if not saas_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SaaS app not found",
        )
    return saas_app


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    saas_id: str,
    data: CustomerCreate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Customer:
    """Create a new customer (syncs to Stripe)."""
    saas_app = await get_saas_app_or_404(saas_id, db)

    # Check if customer with external_id already exists
    result = await db.execute(
        select(Customer).where(
            Customer.saas_app_id == saas_id,
            Customer.external_id == data.external_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Customer with external_id '{data.external_id}' already exists",
        )

    stripe_service = get_stripe_service()

    # Create customer in Stripe
    stripe_customer = stripe_service.create_customer(
        saas_id=saas_app.id,
        email=data.email,
        name=data.name,
        external_id=data.external_id,
        metadata=data.extra_data,
    )

    # Create local customer record
    customer = Customer(
        saas_app_id=saas_app.id,
        external_id=data.external_id,
        stripe_customer_id=stripe_customer.id,
        email=data.email,
        name=data.name,
        extra_data=data.extra_data,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    logger.info(f"Created customer: {customer.email} ({customer.id}) for SaaS {saas_app.slug}")
    return customer


@router.get("", response_model=list[CustomerResponse])
async def list_customers(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(settings.list_default_limit, ge=1, le=settings.list_max_limit),
    offset: int = Query(0, ge=0),
) -> list[Customer]:
    """List all customers for a SaaS app."""
    await get_saas_app_or_404(saas_id, db)

    query = (
        select(Customer)
        .where(Customer.saas_app_id == saas_id)
        .order_by(Customer.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    saas_id: str,
    customer_id: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Customer:
    """Get a customer by ID."""
    await get_saas_app_or_404(saas_id, db)

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.saas_app_id == saas_id,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    saas_id: str,
    customer_id: str,
    data: CustomerUpdate,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Customer:
    """Update a customer (syncs to Stripe)."""
    await get_saas_app_or_404(saas_id, db)

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.saas_app_id == saas_id,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    stripe_service = get_stripe_service()
    update_data = data.model_dump(exclude_unset=True)

    # Update in Stripe
    stripe_service.update_customer(
        stripe_customer_id=customer.stripe_customer_id,
        email=update_data.get("email"),
        name=update_data.get("name"),
        metadata=update_data.get("extra_data"),
    )

    # Update local record
    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.flush()
    await db.refresh(customer)

    logger.info(f"Updated customer: {customer.email} ({customer.id})")
    return customer


@router.get("/{customer_id}/portal", response_model=CustomerPortalResponse)
async def get_customer_portal(
    saas_id: str,
    customer_id: str,
    return_url: str,
    _auth: Annotated[AuthContext, Depends(require_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerPortalResponse:
    """Generate a Customer Portal URL for managing billing.

    ``return_url`` must be covered by the checkout URL allow-list of the SaaS app.
    """
    saas_app = await get_saas_app_or_404(saas_id, db)
    try:
        ensure_allowed_redirect(saas_app, return_url, "return_url")
    except RedirectNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.saas_app_id == saas_id,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    stripe_service = get_stripe_service()
    session = stripe_service.create_customer_portal_session(
        stripe_customer_id=customer.stripe_customer_id,
        return_url=return_url,
    )

    return CustomerPortalResponse(url=session.url)
