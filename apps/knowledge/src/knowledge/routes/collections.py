# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import Auth
from knowledge.database import get_db
from knowledge.models.enums import OwnerType
from knowledge.schemas.collection import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)
from knowledge.services.collection_access import CollectionAccessService
from knowledge.services.collections import CollectionService

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    data: CollectionCreate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
    organization_id: UUID | None = Query(
        None,
        description="Organization ID for creating an org collection. If not provided, creates a personal collection.",
    ),
) -> CollectionResponse:
    """Create a new collection.

    By default, creates a personal collection owned by the authenticated user.
    Pass organization_id to create an organization-owned collection.
    """
    auth.require_scope("collections:write")

    service = CollectionService(db)

    # Determine owner type and ID
    if organization_id:
        # Creating organization collection
        owner_type = OwnerType.ORGANIZATION
        owner_id = organization_id

        # Check if user can create collections in this org
        access_service = CollectionAccessService(db)
        can_create = await access_service.check_org_can_create_collection(
            auth.user_id, organization_id
        )
        if not can_create:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create collections in this organization",
            )
    else:
        # Creating personal collection
        owner_type = OwnerType.USER
        owner_id = auth.user_id

    # Check if slug already exists for this owner
    existing = await service.get_by_slug_for_owner(owner_type, owner_id, data.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Collection with slug '{data.slug}' already exists",
        )

    collection = await service.create_for_owner(owner_type, owner_id, data)
    return CollectionResponse.model_validate(collection)


@router.get("", response_model=list[CollectionResponse])
async def list_collections(
    auth: Auth,
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 100,
    owner_type: OwnerType | None = Query(
        None,
        description="Filter by owner type: 'user' for personal collections, 'organization' for org collections",
    ),
    organization_id: UUID | None = Query(
        None,
        description="Filter to a specific organization's collections",
    ),
    include_shared: bool = Query(
        True,
        description="Include collections shared with you via collaboration",
    ),
) -> list[CollectionResponse]:
    """List all collections accessible to the authenticated user.

    This includes:
    - Personal collections owned by the user
    - Collections the user collaborates on (if include_shared=true)
    - Collections in organizations the user belongs to
    """
    auth.require_scope("collections:read")

    service = CollectionService(db)

    # If filtering by specific owner type and org, use the owner-based method
    if owner_type == OwnerType.USER and not organization_id:
        # Only personal collections
        collections = await service.list_for_owner(OwnerType.USER, auth.user_id, offset, limit)
    elif owner_type == OwnerType.ORGANIZATION or organization_id:
        # Organization collections - verify membership first
        if organization_id:
            # Check if user is member of this org by trying to get org access
            from sqlalchemy import select

            from knowledge.models import OrganizationMember

            result = await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == auth.user_id,
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this organization",
                )
            collections = await service.list_for_owner(
                OwnerType.ORGANIZATION, organization_id, offset, limit
            )
        else:
            # All organization collections user has access to
            collections = await service.list_accessible(
                auth.user_id,
                include_owned=False,
                include_collaborated=False,
                include_organization=True,
                offset=offset,
                limit=limit,
            )
    else:
        # All accessible collections
        collections = await service.list_accessible(
            auth.user_id,
            include_owned=True,
            include_collaborated=include_shared,
            include_organization=True,
            organization_id=organization_id,
            offset=offset,
            limit=limit,
        )

    return [CollectionResponse.model_validate(c) for c in collections]


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: str,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    """Get a collection by ID or slug.

    Returns the collection if the user has any access to it
    (owner, collaborator, or organization member).
    """
    auth.require_scope("collections:read")

    service = CollectionService(db)

    # Try to parse as UUID
    try:
        coll_uuid = UUID(collection_id)
        collection = await service.get_accessible(auth.user_id, coll_uuid)
    except ValueError:
        # Not a UUID, could be a slug - need to search across accessible collections
        # For slugs, we need to check personal first, then organizations
        collection = await service.get_by_slug_for_owner(
            OwnerType.USER, auth.user_id, collection_id
        )
        if not collection:
            # Try to find in organizations user belongs to
            from sqlalchemy import select

            from knowledge.models import OrganizationMember

            result = await db.execute(
                select(OrganizationMember.organization_id).where(
                    OrganizationMember.user_id == auth.user_id
                )
            )
            org_ids = [row[0] for row in result.all()]

            for org_id in org_ids:
                collection = await service.get_by_slug_for_owner(
                    OwnerType.ORGANIZATION, org_id, collection_id
                )
                if collection:
                    break

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    return CollectionResponse.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: UUID,
    data: CollectionUpdate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    """Update a collection.

    Requires write access to the collection (owner, admin collaborator, or org admin).
    """
    auth.require_scope("collections:write")

    service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get the collection and check access
    collection = await service.get_accessible(auth.user_id, collection_id)

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Check write permission
    can_write = await access_service.can_write(auth.user_id, collection)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this collection",
        )

    # Apply updates
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(collection, field, value)

    await db.flush()
    await db.refresh(collection)

    return CollectionResponse.model_validate(collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a collection and all its documents.

    Only the collection owner can delete the collection.
    """
    auth.require_scope("collections:write")

    service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get the collection and check access
    collection = await service.get_accessible(auth.user_id, collection_id)

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Check delete permission (only owner)
    can_delete = await access_service.can_delete(auth.user_id, collection)
    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the collection owner can delete this collection",
        )

    await db.delete(collection)
    await db.flush()
