# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Service for managing collection invitations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import CollectionCollaborator, CollectionInvitation
from knowledge.models.enums import CollaboratorPermission, InvitationStatus


class CollectionInvitationService:
    """Service for managing collection invitations.

    Handles creating, accepting, and revoking invitations
    to collaborate on collections.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        collection_id: UUID,
        email: str,
        permission: CollaboratorPermission,
        invited_by: UUID,
        expires_at: datetime | None = None,
    ) -> CollectionInvitation:
        """Create a new collection invitation.

        Args:
            collection_id: The collection ID.
            email: The email address to invite.
            permission: The permission level for the invitee.
            invited_by: The user creating the invitation.
            expires_at: Optional custom expiration time.

        Returns:
            The created invitation.

        Raises:
            ValueError: If there's already a pending invitation for this email.
        """
        # Check for existing pending invitation
        existing = await self.get_pending_for_email(collection_id, email)
        if existing:
            raise ValueError("There is already a pending invitation for this email address")

        invitation = CollectionInvitation(
            collection_id=collection_id,
            email=email.lower(),
            permission=permission,
            token=CollectionInvitation.generate_token(),
            invited_by=invited_by,
            expires_at=expires_at or CollectionInvitation.default_expiry(),
        )
        self.db.add(invitation)
        await self.db.flush()
        await self.db.refresh(invitation)
        return invitation

    async def get_by_id(self, invitation_id: UUID) -> CollectionInvitation | None:
        """Get an invitation by ID.

        Args:
            invitation_id: The invitation ID.

        Returns:
            The invitation or None if not found.
        """
        result = await self.db.execute(
            select(CollectionInvitation).where(CollectionInvitation.id == invitation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> CollectionInvitation | None:
        """Get an invitation by token.

        Args:
            token: The invitation token.

        Returns:
            The invitation or None if not found.
        """
        result = await self.db.execute(
            select(CollectionInvitation).where(CollectionInvitation.token == token)
        )
        return result.scalar_one_or_none()

    async def get_pending_for_email(
        self,
        collection_id: UUID,
        email: str,
    ) -> CollectionInvitation | None:
        """Get a pending invitation for a specific email.

        Args:
            collection_id: The collection ID.
            email: The email address.

        Returns:
            The pending invitation or None if not found.
        """
        result = await self.db.execute(
            select(CollectionInvitation).where(
                CollectionInvitation.collection_id == collection_id,
                CollectionInvitation.email == email.lower(),
                CollectionInvitation.status == InvitationStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_collection(
        self,
        collection_id: UUID,
        status: InvitationStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CollectionInvitation]:
        """List invitations for a collection.

        Args:
            collection_id: The collection ID.
            status: Optional filter by status.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of invitations.
        """
        query = select(CollectionInvitation).where(
            CollectionInvitation.collection_id == collection_id
        )

        if status:
            query = query.where(CollectionInvitation.status == status)

        result = await self.db.execute(
            query.order_by(CollectionInvitation.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_pending_for_collection(
        self,
        collection_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CollectionInvitation]:
        """List pending invitations for a collection.

        Args:
            collection_id: The collection ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of pending invitations.
        """
        return await self.list_for_collection(
            collection_id, InvitationStatus.PENDING, offset, limit
        )

    async def list_for_email(
        self,
        email: str,
        status: InvitationStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CollectionInvitation]:
        """List invitations for an email address.

        Args:
            email: The email address.
            status: Optional filter by status.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of invitations.
        """
        query = select(CollectionInvitation).where(CollectionInvitation.email == email.lower())

        if status:
            query = query.where(CollectionInvitation.status == status)

        result = await self.db.execute(
            query.order_by(CollectionInvitation.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_pending_for_email(
        self,
        email: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[CollectionInvitation]:
        """List pending invitations for an email address.

        Args:
            email: The email address.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of pending invitations.
        """
        return await self.list_for_email(email, InvitationStatus.PENDING, offset, limit)

    async def accept(
        self,
        token: str,
        user_id: UUID,
    ) -> tuple[CollectionInvitation, CollectionCollaborator] | None:
        """Accept an invitation and create a collaborator.

        Args:
            token: The invitation token.
            user_id: The user accepting the invitation.

        Returns:
            Tuple of (invitation, collaborator) or None if invalid.

        Raises:
            ValueError: If invitation is expired, already accepted, or revoked.
        """
        invitation = await self.get_by_token(token)
        if not invitation:
            return None

        if not invitation.is_valid:
            if invitation.is_expired:
                # Mark as expired if not already
                if invitation.status == InvitationStatus.PENDING:
                    invitation.mark_expired()
                    await self.db.flush()
                raise ValueError("Invitation has expired")
            raise ValueError(f"Invitation is {invitation.status.value}")

        # Check if user is already a collaborator
        from knowledge.services.collaborators import CollaboratorService

        collab_service = CollaboratorService(self.db)
        existing = await collab_service.get(invitation.collection_id, user_id)
        if existing:
            # Accept the invitation but don't create duplicate collaborator
            invitation.accept(user_id)
            await self.db.flush()
            await self.db.refresh(invitation)
            return (invitation, existing)

        # Create the collaborator
        collaborator = await collab_service.add(
            collection_id=invitation.collection_id,
            user_id=user_id,
            permission=invitation.permission,
            invited_by=invitation.invited_by,
        )

        # Mark invitation as accepted
        invitation.accept(user_id)
        await self.db.flush()
        await self.db.refresh(invitation)

        return (invitation, collaborator)

    async def revoke(self, invitation_id: UUID) -> bool:
        """Revoke an invitation.

        Args:
            invitation_id: The invitation ID.

        Returns:
            True if revoked, False if not found or already processed.
        """
        invitation = await self.get_by_id(invitation_id)
        if not invitation:
            return False

        if invitation.status != InvitationStatus.PENDING:
            return False

        invitation.revoke()
        await self.db.flush()
        return True

    async def revoke_by_token(self, token: str) -> bool:
        """Revoke an invitation by token.

        Args:
            token: The invitation token.

        Returns:
            True if revoked, False if not found or already processed.
        """
        invitation = await self.get_by_token(token)
        if not invitation:
            return False

        if invitation.status != InvitationStatus.PENDING:
            return False

        invitation.revoke()
        await self.db.flush()
        return True

    async def expire_old_invitations(self) -> int:
        """Mark expired invitations as expired.

        Should be called periodically to clean up old invitations.

        Returns:
            Number of invitations marked as expired.
        """
        from sqlalchemy import update

        result = await self.db.execute(
            update(CollectionInvitation)
            .where(
                CollectionInvitation.status == InvitationStatus.PENDING,
                CollectionInvitation.expires_at < datetime.now(UTC),
            )
            .values(status=InvitationStatus.EXPIRED)
        )
        await self.db.flush()
        return result.rowcount  # type: ignore[attr-defined]

    async def delete_old_invitations(self, days: int = 30) -> int:
        """Delete old processed invitations.

        Args:
            days: Delete invitations older than this many days.

        Returns:
            Number of invitations deleted.
        """
        from datetime import timedelta

        from sqlalchemy import delete

        cutoff = datetime.now(UTC) - timedelta(days=days)

        result = await self.db.execute(
            delete(CollectionInvitation).where(
                CollectionInvitation.status != InvitationStatus.PENDING,
                CollectionInvitation.created_at < cutoff,
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore[attr-defined]

    async def count_pending_for_collection(self, collection_id: UUID) -> int:
        """Count pending invitations for a collection.

        Args:
            collection_id: The collection ID.

        Returns:
            Number of pending invitations.
        """
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(CollectionInvitation.id)).where(
                CollectionInvitation.collection_id == collection_id,
                CollectionInvitation.status == InvitationStatus.PENDING,
            )
        )
        return result.scalar() or 0

    async def resend(
        self,
        invitation_id: UUID,
        new_expires_at: datetime | None = None,
    ) -> CollectionInvitation | None:
        """Resend an invitation with a new token and expiry.

        Args:
            invitation_id: The invitation ID.
            new_expires_at: Optional new expiration time.

        Returns:
            The updated invitation or None if not found or not pending.
        """
        invitation = await self.get_by_id(invitation_id)
        if not invitation:
            return None

        if invitation.status != InvitationStatus.PENDING:
            return None

        # Generate new token and reset expiry
        invitation.token = CollectionInvitation.generate_token()
        invitation.expires_at = new_expires_at or CollectionInvitation.default_expiry()
        await self.db.flush()
        await self.db.refresh(invitation)
        return invitation
