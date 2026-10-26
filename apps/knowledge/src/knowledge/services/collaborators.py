# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Service for managing collection collaborators."""

from __future__ import annotations

import builtins
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import CollectionCollaborator
from knowledge.models.enums import CollaboratorPermission


class CollaboratorService:
    """Service for managing collection collaborators.

    Collaborators are users who have been granted access to a collection
    without being the owner or an organization member.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        collection_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> builtins.list[CollectionCollaborator]:
        """List all collaborators for a collection.

        Args:
            collection_id: The collection ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of collaborators.
        """
        result = await self.db.execute(
            select(CollectionCollaborator)
            .where(CollectionCollaborator.collection_id == collection_id)
            .order_by(CollectionCollaborator.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(
        self,
        collection_id: UUID,
        user_id: UUID,
    ) -> CollectionCollaborator | None:
        """Get a specific collaborator.

        Args:
            collection_id: The collection ID.
            user_id: The collaborator's user ID.

        Returns:
            The collaborator or None if not found.
        """
        result = await self.db.execute(
            select(CollectionCollaborator).where(
                CollectionCollaborator.collection_id == collection_id,
                CollectionCollaborator.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(
        self,
        collection_id: UUID,
        user_id: UUID,
        permission: CollaboratorPermission,
        invited_by: UUID,
    ) -> CollectionCollaborator:
        """Add a collaborator to a collection.

        Args:
            collection_id: The collection ID.
            user_id: The user to add as collaborator.
            permission: The permission level (read/write/admin).
            invited_by: The user who invited this collaborator.

        Returns:
            The created collaborator.

        Raises:
            ValueError: If user is already a collaborator.
        """
        # Check if already a collaborator
        existing = await self.get(collection_id, user_id)
        if existing:
            raise ValueError("User is already a collaborator on this collection")

        collaborator = CollectionCollaborator(
            collection_id=collection_id,
            user_id=user_id,
            permission=permission,
            invited_by=invited_by,
        )
        self.db.add(collaborator)
        await self.db.flush()
        await self.db.refresh(collaborator)
        return collaborator

    async def update_permission(
        self,
        collection_id: UUID,
        user_id: UUID,
        permission: CollaboratorPermission,
    ) -> CollectionCollaborator | None:
        """Update a collaborator's permission level.

        Args:
            collection_id: The collection ID.
            user_id: The collaborator's user ID.
            permission: The new permission level.

        Returns:
            The updated collaborator or None if not found.
        """
        collaborator = await self.get(collection_id, user_id)
        if not collaborator:
            return None

        collaborator.permission = permission
        await self.db.flush()
        await self.db.refresh(collaborator)
        return collaborator

    async def remove(
        self,
        collection_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove a collaborator from a collection.

        Args:
            collection_id: The collection ID.
            user_id: The collaborator's user ID.

        Returns:
            True if removed, False if not found.
        """
        collaborator = await self.get(collection_id, user_id)
        if not collaborator:
            return False

        await self.db.delete(collaborator)
        await self.db.flush()
        return True

    async def count(self, collection_id: UUID) -> int:
        """Count collaborators for a collection.

        Args:
            collection_id: The collection ID.

        Returns:
            Number of collaborators.
        """
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(CollectionCollaborator.id)).where(
                CollectionCollaborator.collection_id == collection_id
            )
        )
        return result.scalar() or 0

    async def get_user_collaborations(
        self,
        user_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> builtins.list[CollectionCollaborator]:
        """Get all collections a user collaborates on.

        Args:
            user_id: The user's ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of collaborations.
        """
        result = await self.db.execute(
            select(CollectionCollaborator)
            .where(CollectionCollaborator.user_id == user_id)
            .order_by(CollectionCollaborator.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def is_collaborator(
        self,
        collection_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Check if a user is a collaborator on a collection.

        Args:
            collection_id: The collection ID.
            user_id: The user's ID.

        Returns:
            True if user is a collaborator.
        """
        collaborator = await self.get(collection_id, user_id)
        return collaborator is not None

    async def get_permission(
        self,
        collection_id: UUID,
        user_id: UUID,
    ) -> CollaboratorPermission | None:
        """Get a user's permission level on a collection.

        Args:
            collection_id: The collection ID.
            user_id: The user's ID.

        Returns:
            The permission level or None if not a collaborator.
        """
        collaborator = await self.get(collection_id, user_id)
        if not collaborator:
            return None
        return collaborator.permission

    async def remove_all_for_collection(self, collection_id: UUID) -> int:
        """Remove all collaborators from a collection.

        Useful when deleting a collection.

        Args:
            collection_id: The collection ID.

        Returns:
            Number of collaborators removed.
        """
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(CollectionCollaborator).where(
                CollectionCollaborator.collection_id == collection_id
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore[attr-defined]

    async def remove_user_from_all(self, user_id: UUID) -> int:
        """Remove a user from all collections they collaborate on.

        Useful when deleting a user account.

        Args:
            user_id: The user's ID.

        Returns:
            Number of collaborations removed.
        """
        from sqlalchemy import delete

        result = await self.db.execute(
            delete(CollectionCollaborator).where(CollectionCollaborator.user_id == user_id)
        )
        await self.db.flush()
        return result.rowcount  # type: ignore[attr-defined]
