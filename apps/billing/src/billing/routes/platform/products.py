# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Product management routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.auth import AuthContext
from billing.database import get_db
from billing.models import BillingProduct, SaasApp
from billing.partition import require_saas_scopes
from billing.schemas import ProductCreate, ProductResponse, ProductUpdate
from billing.services import get_stripe_service
from billing.services.stripe_service import build_stripe_description

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platform/{saas_id}/products", tags=["Platform - Products"])


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


async def ensure_slug_available(
    db: AsyncSession, saas_id: str, slug: str, exclude_id: str | None = None
) -> None:
    """Raise 409 if another product of the SaaS application already uses the slug."""
    query = select(BillingProduct.id).where(
        BillingProduct.saas_app_id == saas_id, BillingProduct.slug == slug
    )
    if exclude_id:
        query = query.where(BillingProduct.id != exclude_id)
    if (await db.execute(query)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A product with slug '{slug}' already exists for this SaaS app",
        )


def with_slug(metadata: dict | None, slug: str) -> dict:
    """Return the product metadata with ``slug`` mirrored, for clients reading it there."""
    return {**(metadata or {}), "slug": slug}


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    saas_id: str,
    data: ProductCreate,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingProduct:
    """Create a new product (syncs to Stripe)."""
    saas_app = await get_saas_app_or_404(saas_id, db)
    assert data.slug is not None  # resolved by the schema
    await ensure_slug_available(db, saas_app.id, data.slug)
    stripe_service = get_stripe_service()
    extra_data = with_slug(data.metadata, data.slug)

    # Build description with features for Stripe
    stripe_description = build_stripe_description(data.description, extra_data)
    stripe_product = stripe_service.create_product(
        saas_id=saas_app.id,
        name=data.name,
        description=stripe_description,
        metadata=extra_data,
    )

    # Create local product record
    product = BillingProduct(
        saas_app_id=saas_app.id,
        stripe_product_id=stripe_product.id,
        slug=data.slug,
        name=data.name,
        description=data.description,
        extra_data=extra_data,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)

    logger.info(f"Created product: {product.name} ({product.id}) for SaaS {saas_app.slug}")
    return product


@router.get("", response_model=list[ProductResponse])
async def list_products(
    saas_id: str,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: bool = False,
) -> list[BillingProduct]:
    """List all products for a SaaS app."""
    await get_saas_app_or_404(saas_id, db)

    query = select(BillingProduct).where(BillingProduct.saas_app_id == saas_id)
    if not include_inactive:
        query = query.where(BillingProduct.is_active == True)  # noqa: E712
    query = query.order_by(BillingProduct.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    saas_id: str,
    product_id: str,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:platform:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingProduct:
    """Get a product by ID."""
    await get_saas_app_or_404(saas_id, db)

    result = await db.execute(
        select(BillingProduct).where(
            BillingProduct.id == product_id,
            BillingProduct.saas_app_id == saas_id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    saas_id: str,
    product_id: str,
    data: ProductUpdate,
    _auth: Annotated[AuthContext, Depends(require_saas_scopes("billing:platform:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BillingProduct:
    """Update a product (syncs to Stripe)."""
    await get_saas_app_or_404(saas_id, db)

    result = await db.execute(
        select(BillingProduct).where(
            BillingProduct.id == product_id,
            BillingProduct.saas_app_id == saas_id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    stripe_service = get_stripe_service()
    update_data = data.model_dump(exclude_unset=True)

    new_slug = update_data.get("slug")
    if new_slug and new_slug != product.slug:
        await ensure_slug_available(db, saas_id, new_slug, exclude_id=product.id)
    effective_slug = new_slug or product.slug
    if "metadata" in update_data or new_slug:
        update_data["metadata"] = with_slug(
            update_data.get("metadata", product.extra_data), effective_slug
        )

    # Compute effective description and extra_data for Stripe
    effective_description = update_data.get("description", product.description)
    effective_extra_data = update_data.get("metadata", product.extra_data)
    stripe_description = build_stripe_description(effective_description, effective_extra_data)

    # Update in Stripe
    stripe_service.update_product(
        stripe_product_id=product.stripe_product_id,
        name=update_data.get("name"),
        description=stripe_description,
        active=update_data.get("is_active"),
        metadata=update_data.get("metadata"),
    )

    # Update local record (map metadata -> extra_data for model)
    for field, value in update_data.items():
        model_field = "extra_data" if field == "metadata" else field
        setattr(product, model_field, value)

    await db.flush()
    await db.refresh(product)

    logger.info(f"Updated product: {product.name} ({product.id})")
    return product
