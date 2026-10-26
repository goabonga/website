# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collaborator routes for collection sharing."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import Auth
from knowledge.database import get_db
from knowledge.models.enums import CollaboratorPermission
from knowledge.services.collaborators import CollaboratorService
from knowledge.services.collection_access import CollectionAccessService
from knowledge.services.collections import CollectionService

router = APIRouter(prefix="/collections/{collection_id}/collaborators", tags=["Collaborators"])


class CollaboratorResponse(BaseModel):
    """Response model for a collaborator."""

    id: UUID
    collection_id: UUID
    user_id: UUID
    permission: CollaboratorPermission
    invited_by: UUID

    model_config = ConfigDict(from_attributes=True)


class CollaboratorCreate(BaseModel):
    """Request model for adding a collaborator."""

    user_id: UUID
    permission: CollaboratorPermission = CollaboratorPermission.READ


class CollaboratorUpdate(BaseModel):
    """Request model for updating a collaborator."""

    permission: CollaboratorPermission


class InvitationCreate(BaseModel):
    """Request model for creating an invitation."""

    email: EmailStr
    permission: CollaboratorPermission = CollaboratorPermission.READ


class InvitationResponse(BaseModel):
    """Response model for an invitation."""

    id: UUID
    collection_id: UUID
    email: str
    permission: CollaboratorPermission
    status: str
    invited_by: UUID
    token: str | None = None  # Only returned to the creator

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[CollaboratorResponse])
async def list_collaborators(
    collection_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 100,
) -> list[CollaboratorResponse]:
    """List all collaborators for a collection.

    Requires at least read access to the collection.
    """
    auth.require_scope("collections:read")

    collection_service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get collection and verify access
    collection = await collection_service.get_accessible(auth.user_id, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Verify at least read access
    can_read = await access_service.can_read(auth.user_id, collection)
    if not can_read:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this collection",
        )

    collab_service = CollaboratorService(db)
    collaborators = await collab_service.list(collection_id, offset, limit)

    return [CollaboratorResponse.model_validate(c) for c in collaborators]


@router.post("", response_model=CollaboratorResponse, status_code=status.HTTP_201_CREATED)
async def add_collaborator(
    collection_id: UUID,
    data: CollaboratorCreate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> CollaboratorResponse:
    """Add a collaborator to a collection.

    Requires admin access to the collection.
    """
    auth.require_scope("collections:write")

    collection_service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get collection and verify access
    collection = await collection_service.get_accessible(auth.user_id, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Verify admin access
    can_invite = await access_service.can_invite(auth.user_id, collection)
    if not can_invite:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to add collaborators to this collection",
        )

    # Cannot add self as collaborator
    if data.user_id == auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add yourself as a collaborator",
        )

    collab_service = CollaboratorService(db)

    try:
        collaborator = await collab_service.add(
            collection_id=collection_id,
            user_id=data.user_id,
            permission=data.permission,
            invited_by=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return CollaboratorResponse.model_validate(collaborator)


@router.patch("/{user_id}", response_model=CollaboratorResponse)
async def update_collaborator(
    collection_id: UUID,
    user_id: UUID,
    data: CollaboratorUpdate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> CollaboratorResponse:
    """Update a collaborator's permission level.

    Requires admin access to the collection.
    """
    auth.require_scope("collections:write")

    collection_service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get collection and verify access
    collection = await collection_service.get_accessible(auth.user_id, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # Verify admin access
    can_invite = await access_service.can_invite(auth.user_id, collection)
    if not can_invite:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify collaborators on this collection",
        )

    collab_service = CollaboratorService(db)
    collaborator = await collab_service.update_permission(
        collection_id=collection_id,
        user_id=user_id,
        permission=data.permission,
    )

    if not collaborator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaborator not found",
        )

    return CollaboratorResponse.model_validate(collaborator)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collaborator(
    collection_id: UUID,
    user_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a collaborator from a collection.

    Requires admin access to the collection.
    A collaborator can also remove themselves.
    """
    auth.require_scope("collections:write")

    collection_service = CollectionService(db)
    access_service = CollectionAccessService(db)

    # Get collection and verify access
    collection = await collection_service.get_accessible(auth.user_id, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        )

    # User can remove themselves, or admin can remove anyone
    if user_id != auth.user_id:
        can_invite = await access_service.can_invite(auth.user_id, collection)
        if not can_invite:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to remove collaborators from this collection",
            )

    collab_service = CollaboratorService(db)
    removed = await collab_service.remove(collection_id, user_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaborator not found",
        )
