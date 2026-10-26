# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection invitation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.auth.dependencies import Auth
from knowledge.database import get_db
from knowledge.models.enums import CollaboratorPermission, InvitationStatus
from knowledge.services.collection_access import CollectionAccessService
from knowledge.services.collection_invitations import CollectionInvitationService
from knowledge.services.collections import CollectionService

# Router for collection-scoped invitations
collection_router = APIRouter(
    prefix="/collections/{collection_id}/invitations",
    tags=["Collection Invitations"],
)

# Router for public invitation endpoints
public_router = APIRouter(
    prefix="/collection-invites",
    tags=["Collection Invitations"],
)


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
    status: InvitationStatus
    invited_by: UUID

    model_config = ConfigDict(from_attributes=True)


class InvitationDetailResponse(InvitationResponse):
    """Detailed response including token (for creator only)."""

    token: str


class InvitationPublicResponse(BaseModel):
    """Public response for viewing an invitation."""

    id: UUID
    collection_id: UUID
    collection_name: str
    permission: CollaboratorPermission
    is_valid: bool
    is_expired: bool


class AcceptInvitationResponse(BaseModel):
    """Response after accepting an invitation."""

    message: str
    collection_id: UUID
    permission: CollaboratorPermission


# ============================================================================
# Collection-scoped routes
# ============================================================================


@collection_router.get("", response_model=list[InvitationResponse])
async def list_invitations(
    collection_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
    status_filter: InvitationStatus | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[InvitationResponse]:
    """List invitations for a collection.

    Requires admin access to the collection.
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

    # Verify admin access to see invitations
    can_admin = await access_service.can_admin(auth.user_id, collection)
    if not can_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view invitations for this collection",
        )

    invitation_service = CollectionInvitationService(db)
    invitations = await invitation_service.list_for_collection(
        collection_id, status_filter, offset, limit
    )

    return [InvitationResponse.model_validate(i) for i in invitations]


@collection_router.post(
    "",
    response_model=InvitationDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    collection_id: UUID,
    data: InvitationCreate,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> InvitationDetailResponse:
    """Create an invitation to collaborate on a collection.

    Requires admin access to the collection.
    Returns the invitation with token for sharing.
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
            detail="You don't have permission to invite collaborators to this collection",
        )

    invitation_service = CollectionInvitationService(db)

    try:
        invitation = await invitation_service.create(
            collection_id=collection_id,
            email=data.email,
            permission=data.permission,
            invited_by=auth.user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return InvitationDetailResponse.model_validate(invitation)


@collection_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    collection_id: UUID,
    invitation_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a pending invitation.

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
            detail="You don't have permission to revoke invitations for this collection",
        )

    invitation_service = CollectionInvitationService(db)

    # Get invitation and verify it belongs to this collection
    invitation = await invitation_service.get_by_id(invitation_id)
    if not invitation or invitation.collection_id != collection_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    revoked = await invitation_service.revoke(invitation_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been processed",
        )


@collection_router.post("/{invitation_id}/resend", response_model=InvitationDetailResponse)
async def resend_invitation(
    collection_id: UUID,
    invitation_id: UUID,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> InvitationDetailResponse:
    """Resend an invitation with a new token and expiry.

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
            detail="You don't have permission to resend invitations for this collection",
        )

    invitation_service = CollectionInvitationService(db)

    # Get invitation and verify it belongs to this collection
    invitation = await invitation_service.get_by_id(invitation_id)
    if not invitation or invitation.collection_id != collection_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    updated = await invitation_service.resend(invitation_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been processed and cannot be resent",
        )

    return InvitationDetailResponse.model_validate(updated)


# ============================================================================
# Public routes for accepting invitations
# ============================================================================


@public_router.get("/{token}", response_model=InvitationPublicResponse)
async def get_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InvitationPublicResponse:
    """View an invitation by token.

    Public endpoint - no authentication required.
    """
    invitation_service = CollectionInvitationService(db)
    invitation = await invitation_service.get_by_token(token)

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    # Get collection name
    collection_service = CollectionService(db)
    collection = await collection_service.get_by_id_global(invitation.collection_id)

    return InvitationPublicResponse(
        id=invitation.id,
        collection_id=invitation.collection_id,
        collection_name=collection.name if collection else "Unknown Collection",
        permission=invitation.permission,
        is_valid=invitation.is_valid,
        is_expired=invitation.is_expired,
    )


@public_router.post("/{token}/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(
    token: str,
    auth: Auth,
    db: AsyncSession = Depends(get_db),
) -> AcceptInvitationResponse:
    """Accept an invitation to collaborate on a collection.

    Requires authentication.
    """
    invitation_service = CollectionInvitationService(db)

    try:
        result = await invitation_service.accept(token, auth.user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    invitation, collaborator = result

    return AcceptInvitationResponse(
        message="Invitation accepted successfully",
        collection_id=invitation.collection_id,
        permission=collaborator.permission,
    )
