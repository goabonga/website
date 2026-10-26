# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Service for checking collection access permissions."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models import (
    Collection,
    CollectionCollaborator,
    Organization,
    OrganizationMember,
)
from knowledge.models.enums import CollaboratorPermission, OrganizationMemberRole, OwnerType


class AccessLevel(StrEnum):
    """Resolved access level for a user on a collection."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


class CollectionAccessService:
    """Service for determining user access to collections.

    This service resolves the effective access level for a user on a collection,
    taking into account:
    1. Direct ownership (user owns the collection)
    2. Organization membership (for org-owned collections)
    3. Collection collaboration (invited collaborators)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_access_level(self, user_id: UUID, collection: Collection) -> AccessLevel:
        """Determine a user's access level to a collection.

        Access hierarchy (highest wins):
        1. Owner (personal collection owner or org owner)
        2. Admin (org admin or collection admin collaborator)
        3. Write (org member with write or collection write collaborator)
        4. Read (org member or collection read collaborator)
        5. None (no access)

        Args:
            user_id: The user to check access for.
            collection: The collection to check access on.

        Returns:
            The user's effective access level.
        """
        # Check if user is the direct owner (personal collection)
        if collection.owner_type == OwnerType.USER and collection.owner_id == user_id:
            return AccessLevel.OWNER

        # Check organization membership for org collections
        if collection.owner_type == OwnerType.ORGANIZATION:
            org_access = await self._get_org_access(user_id, collection.owner_id)
            if org_access != AccessLevel.NONE:
                # Check for higher access via collaborator
                collab_access = await self._get_collaborator_access(user_id, collection.id)
                return max(org_access, collab_access, key=self._access_priority)

        # Check collection-level collaboration
        return await self._get_collaborator_access(user_id, collection.id)

    async def _get_org_access(self, user_id: UUID, organization_id: UUID) -> AccessLevel:
        """Get access level from organization membership.

        Args:
            user_id: The user to check.
            organization_id: The organization to check membership in.

        Returns:
            Access level based on organization role.
        """
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            return AccessLevel.NONE

        if member.role == OrganizationMemberRole.OWNER:
            return AccessLevel.OWNER
        elif member.role == OrganizationMemberRole.ADMIN:
            return AccessLevel.ADMIN
        else:  # MEMBER
            # Org members get write access to org collections by default
            return AccessLevel.WRITE

    async def _get_collaborator_access(self, user_id: UUID, collection_id: UUID) -> AccessLevel:
        """Get access level from collection collaboration.

        Args:
            user_id: The user to check.
            collection_id: The collection to check collaboration on.

        Returns:
            Access level based on collaborator permission.
        """
        result = await self.db.execute(
            select(CollectionCollaborator).where(
                CollectionCollaborator.collection_id == collection_id,
                CollectionCollaborator.user_id == user_id,
            )
        )
        collab = result.scalar_one_or_none()

        if not collab:
            return AccessLevel.NONE

        permission_map = {
            CollaboratorPermission.READ: AccessLevel.READ,
            CollaboratorPermission.WRITE: AccessLevel.WRITE,
            CollaboratorPermission.ADMIN: AccessLevel.ADMIN,
        }
        return permission_map.get(collab.permission, AccessLevel.NONE)

    def _access_priority(self, level: AccessLevel) -> int:
        """Get priority for access level comparison.

        Higher priority = more permissions.

        Args:
            level: The access level to get priority for.

        Returns:
            Numeric priority (higher = more access).
        """
        priority = {
            AccessLevel.NONE: 0,
            AccessLevel.READ: 1,
            AccessLevel.WRITE: 2,
            AccessLevel.ADMIN: 3,
            AccessLevel.OWNER: 4,
        }
        return priority.get(level, 0)

    async def can_read(self, user_id: UUID, collection: Collection) -> bool:
        """Check if user can read collection.

        Args:
            user_id: The user to check.
            collection: The collection to check access on.

        Returns:
            True if user has at least read access.
        """
        level = await self.get_access_level(user_id, collection)
        return level != AccessLevel.NONE

    async def can_write(self, user_id: UUID, collection: Collection) -> bool:
        """Check if user can write to collection.

        Args:
            user_id: The user to check.
            collection: The collection to check access on.

        Returns:
            True if user has at least write access.
        """
        level = await self.get_access_level(user_id, collection)
        return level in (AccessLevel.WRITE, AccessLevel.ADMIN, AccessLevel.OWNER)

    async def can_admin(self, user_id: UUID, collection: Collection) -> bool:
        """Check if user can administer collection.

        Admin access allows inviting collaborators and changing settings.

        Args:
            user_id: The user to check.
            collection: The collection to check access on.

        Returns:
            True if user has admin or owner access.
        """
        level = await self.get_access_level(user_id, collection)
        return level in (AccessLevel.ADMIN, AccessLevel.OWNER)

    async def can_delete(self, user_id: UUID, collection: Collection) -> bool:
        """Check if user can delete collection.

        Only owners can delete collections.

        Args:
            user_id: The user to check.
            collection: The collection to check access on.

        Returns:
            True if user is the owner.
        """
        level = await self.get_access_level(user_id, collection)
        return level == AccessLevel.OWNER

    async def can_invite(self, user_id: UUID, collection: Collection) -> bool:
        """Check if user can invite collaborators to collection.

        Admin and owner can invite collaborators.

        Args:
            user_id: The user to check.
            collection: The collection to check access on.

        Returns:
            True if user can invite collaborators.
        """
        return await self.can_admin(user_id, collection)

    async def check_org_can_create_collection(self, user_id: UUID, organization_id: UUID) -> bool:
        """Check if user can create a collection in an organization.

        Args:
            user_id: The user to check.
            organization_id: The organization to create in.

        Returns:
            True if user can create collections in the org.
        """
        # Get organization membership
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            return False

        # Owners and admins can always create
        if member.is_admin:
            return True

        # Check organization settings for member creation
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org: Organization | None = result.scalar_one_or_none()  # type: ignore[assignment]

        if not org:
            return False

        return org.allow_member_create_collections
