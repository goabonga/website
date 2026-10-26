# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Collection service for CRUD operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from knowledge.models import Collection, CollectionCollaborator
from knowledge.models.enums import OwnerType
from knowledge.schemas.collection import CollectionCreate, CollectionUpdate


class CollectionService:
    """Service for managing collections.

    Supports polymorphic ownership (user or organization) and
    maintains backward compatibility with tenant-based operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ========== NEW POLYMORPHIC METHODS ==========

    async def create_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        data: CollectionCreate,
    ) -> Collection:
        """Create a new collection for a specific owner.

        Args:
            owner_type: The owner type (user or organization).
            owner_id: The owner's ID (user_id or organization_id).
            data: Collection creation data.

        Returns:
            The created collection.
        """
        collection = Collection(
            owner_type=owner_type,
            owner_id=owner_id,
            # For organization collections, also set organization_id for backward compat
            organization_id=owner_id if owner_type == OwnerType.ORGANIZATION else None,
            name=data.name,
            slug=data.slug,
            description=data.description,
            embedding_model=data.embedding_model,
            dimension=data.dimension,
            metadata_schema=data.metadata_schema,
        )
        self.db.add(collection)
        await self.db.flush()
        await self.db.refresh(collection)
        return collection

    async def get_by_id_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        collection_id: UUID,
    ) -> Collection | None:
        """Get a collection by ID for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            collection_id: The collection ID.

        Returns:
            The collection or None if not found.
        """
        result = await self.db.execute(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        slug: str,
    ) -> Collection | None:
        """Get a collection by slug for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            slug: The collection slug.

        Returns:
            The collection or None if not found.
        """
        result = await self.db.execute(
            select(Collection).where(
                Collection.slug == slug,
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_slug_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        id_or_slug: str,
    ) -> Collection | None:
        """Get a collection by ID or slug for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            id_or_slug: The collection ID or slug.

        Returns:
            The collection or None if not found.
        """
        # Try as UUID first
        try:
            collection_id = UUID(id_or_slug)
            return await self.get_by_id_for_owner(owner_type, owner_id, collection_id)
        except ValueError:
            # Not a valid UUID, try as slug
            return await self.get_by_slug_for_owner(owner_type, owner_id, id_or_slug)

    async def list_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Collection]:
        """List all collections for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of collections.
        """
        result = await self.db.execute(
            select(Collection)
            .where(
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
            .order_by(Collection.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_accessible(
        self,
        user_id: UUID,
        include_owned: bool = True,
        include_collaborated: bool = True,
        include_organization: bool = True,
        organization_id: UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Collection]:
        """List all collections accessible to a user.

        This includes:
        - Collections owned by the user (personal collections)
        - Collections the user collaborates on
        - Collections in organizations the user belongs to

        Args:
            user_id: The user's ID.
            include_owned: Include user's own collections.
            include_collaborated: Include collections user collaborates on.
            include_organization: Include collections from user's organizations.
            organization_id: Filter to specific organization.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of accessible collections.
        """
        from knowledge.models import OrganizationMember

        conditions: list[ColumnElement[bool]] = []

        # User's own collections
        if include_owned:
            conditions.append(
                (Collection.owner_type == OwnerType.USER) & (Collection.owner_id == user_id)
            )

        # Collections user collaborates on
        if include_collaborated:
            # Get collection IDs user collaborates on
            collab_subq = (
                select(CollectionCollaborator.collection_id)
                .where(CollectionCollaborator.user_id == user_id)
                .scalar_subquery()
            )
            conditions.append(Collection.id.in_(collab_subq))

        # Collections in user's organizations
        if include_organization:
            # Get organization IDs user belongs to
            org_subq = (
                select(OrganizationMember.organization_id)
                .where(OrganizationMember.user_id == user_id)
                .scalar_subquery()
            )

            if organization_id:
                # Filter to specific organization (verify user is member)
                conditions.append(
                    (Collection.owner_type == OwnerType.ORGANIZATION)
                    & (Collection.owner_id == organization_id)
                    & (Collection.owner_id.in_(org_subq))
                )
            else:
                conditions.append(
                    (Collection.owner_type == OwnerType.ORGANIZATION)
                    & (Collection.owner_id.in_(org_subq))
                )

        if not conditions:
            return []

        result = await self.db.execute(
            select(Collection)
            .where(or_(*conditions))
            .order_by(Collection.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_accessible(
        self,
        user_id: UUID,
        collection_id: UUID,
    ) -> Collection | None:
        """Get a collection if the user has any access to it.

        This checks ownership, collaboration, and organization membership.
        Use CollectionAccessService to determine the specific access level.

        Args:
            user_id: The user's ID.
            collection_id: The collection ID.

        Returns:
            The collection or None if not accessible.
        """
        from knowledge.models import OrganizationMember

        # First get the collection
        result = await self.db.execute(
            select(Collection)
            .where(Collection.id == collection_id)
            .options(selectinload(Collection.collaborators))
        )
        collection = result.scalar_one_or_none()

        if not collection:
            return None

        # Check if user owns it
        if collection.owner_type == OwnerType.USER and collection.owner_id == user_id:
            return collection

        # Check if user is a collaborator
        for collab in collection.collaborators:
            if collab.user_id == user_id:
                return collection

        # Check if user is in the organization
        if collection.owner_type == OwnerType.ORGANIZATION:
            result = await self.db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == collection.owner_id,
                    OrganizationMember.user_id == user_id,
                )
            )
            if result.scalar_one_or_none():
                return collection

        return None

    async def update_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        collection_id: UUID,
        data: CollectionUpdate,
    ) -> Collection | None:
        """Update a collection for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            collection_id: The collection ID.
            data: Collection update data.

        Returns:
            The updated collection or None if not found.
        """
        collection = await self.get_by_id_for_owner(owner_type, owner_id, collection_id)
        if not collection:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(collection, field, value)

        await self.db.flush()
        await self.db.refresh(collection)
        return collection

    async def delete_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        collection_id: UUID,
    ) -> bool:
        """Delete a collection for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            collection_id: The collection ID.

        Returns:
            True if deleted, False if not found.
        """
        collection = await self.get_by_id_for_owner(owner_type, owner_id, collection_id)
        if not collection:
            return False

        await self.db.delete(collection)
        await self.db.flush()
        return True

    async def count_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
    ) -> int:
        """Count collections for a specific owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.

        Returns:
            Number of collections.
        """
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(Collection.id)).where(
                Collection.owner_type == owner_type,
                Collection.owner_id == owner_id,
            )
        )
        return result.scalar() or 0

    # ========== LEGACY TENANT-BASED METHODS (Backward Compatibility) ==========

    async def create(self, tenant_id: UUID, data: CollectionCreate) -> Collection:
        """Create a new collection for a tenant (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            data: Collection creation data.

        Returns:
            The created collection.
        """
        return await self.create_for_owner(OwnerType.ORGANIZATION, tenant_id, data)

    async def get_by_id(self, tenant_id: UUID, collection_id: UUID) -> Collection | None:
        """Get a collection by ID (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            collection_id: The collection ID.

        Returns:
            The collection or None if not found.
        """
        return await self.get_by_id_for_owner(OwnerType.ORGANIZATION, tenant_id, collection_id)

    async def get_by_slug(self, tenant_id: UUID, slug: str) -> Collection | None:
        """Get a collection by slug (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            slug: The collection slug.

        Returns:
            The collection or None if not found.
        """
        return await self.get_by_slug_for_owner(OwnerType.ORGANIZATION, tenant_id, slug)

    async def get_by_id_or_slug(self, tenant_id: UUID, id_or_slug: str) -> Collection | None:
        """Get a collection by ID or slug (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            id_or_slug: The collection ID or slug.

        Returns:
            The collection or None if not found.
        """
        return await self.get_by_id_or_slug_for_owner(OwnerType.ORGANIZATION, tenant_id, id_or_slug)

    async def list(
        self,
        tenant_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Collection]:
        """List all collections for a tenant (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of collections.
        """
        return await self.list_for_owner(OwnerType.ORGANIZATION, tenant_id, offset, limit)

    async def update(
        self,
        tenant_id: UUID,
        collection_id: UUID,
        data: CollectionUpdate,
    ) -> Collection | None:
        """Update a collection (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            collection_id: The collection ID.
            data: Collection update data.

        Returns:
            The updated collection or None if not found.
        """
        return await self.update_for_owner(OwnerType.ORGANIZATION, tenant_id, collection_id, data)

    async def delete(self, tenant_id: UUID, collection_id: UUID) -> bool:
        """Delete a collection (backward compatibility).

        Args:
            tenant_id: The tenant ID.
            collection_id: The collection ID.

        Returns:
            True if deleted, False if not found.
        """
        return await self.delete_for_owner(OwnerType.ORGANIZATION, tenant_id, collection_id)

    # ========== UTILITY METHODS ==========

    async def increment_document_count(self, collection_id: UUID, increment: int = 1) -> None:
        """Increment the document count for a collection.

        Args:
            collection_id: The collection ID.
            increment: The amount to increment (can be negative).
        """
        result = await self.db.execute(select(Collection).where(Collection.id == collection_id))
        collection = result.scalar_one_or_none()
        if collection:
            collection.document_count += increment
            await self.db.flush()

    async def get_by_id_global(self, collection_id: UUID) -> Collection | None:
        """Get a collection by ID without owner check.

        Use this only for internal operations where access has
        already been verified.

        Args:
            collection_id: The collection ID.

        Returns:
            The collection or None if not found.
        """
        result = await self.db.execute(select(Collection).where(Collection.id == collection_id))
        return result.scalar_one_or_none()

    async def slug_exists_for_owner(
        self,
        owner_type: OwnerType,
        owner_id: UUID,
        slug: str,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Check if a slug already exists for an owner.

        Args:
            owner_type: The owner type.
            owner_id: The owner's ID.
            slug: The slug to check.
            exclude_id: Optional collection ID to exclude (for updates).

        Returns:
            True if slug exists, False otherwise.
        """
        query = select(Collection.id).where(
            Collection.owner_type == owner_type,
            Collection.owner_id == owner_id,
            Collection.slug == slug,
        )

        if exclude_id:
            query = query.where(Collection.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None
