# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-memory fakes used by the behave scenarios.

The routes are exercised for real (routing, validation, scope checks,
serialization). Only the persistence layer is replaced by small in-memory
stand-ins so that no database is needed.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from knowledge.auth.dependencies import AuthContext
from knowledge.auth.models import User
from knowledge.models import Collection
from knowledge.models.enums import OwnerType


class Store:
    """Shared in-memory state of one scenario."""

    def __init__(self):
        self.collections: dict[UUID, Collection] = {}


class FakeSession:
    """Minimal AsyncSession stand-in: flush/refresh are no-ops, delete removes from the store."""

    def __init__(self, store: Store):
        self.store = store
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        self.execute = AsyncMock(return_value=result)

    async def delete(self, obj):
        self.store.collections.pop(obj.id, None)


def make_auth_context(user_id: str, scopes: str, tenant_id: str | None = None) -> AuthContext:
    user = User(id=UUID(user_id), email="user@example.test", scopes=scopes.split())
    return AuthContext(user=user, tenant_id=UUID(tenant_id) if tenant_id else None)


class FakeCollectionService:
    """In-memory implementation of the CollectionService methods used by the routes."""

    def __init__(self, store: Store):
        self.store = store

    async def create_for_owner(self, owner_type, owner_id, data):
        now = datetime.now(UTC)
        collection = Collection(
            id=uuid4(),
            owner_type=owner_type,
            owner_id=owner_id,
            organization_id=owner_id if owner_type == OwnerType.ORGANIZATION else None,
            name=data.name,
            slug=data.slug,
            description=data.description,
            embedding_model=data.embedding_model,
            dimension=data.dimension,
            metadata_schema=data.metadata_schema,
            document_count=0,
            created_at=now,
            updated_at=now,
        )
        self.store.collections[collection.id] = collection
        return collection

    async def get_by_slug_for_owner(self, owner_type, owner_id, slug):
        for collection in self.store.collections.values():
            if (
                collection.owner_type == owner_type
                and collection.owner_id == owner_id
                and collection.slug == slug
            ):
                return collection
        return None

    async def list_for_owner(self, owner_type, owner_id, offset=0, limit=100):
        items = [
            c
            for c in self.store.collections.values()
            if c.owner_type == owner_type and c.owner_id == owner_id
        ]
        return items[offset : offset + limit]

    async def list_accessible(self, user_id, **kwargs):
        items = [
            c
            for c in self.store.collections.values()
            if c.owner_type == OwnerType.USER and c.owner_id == user_id
        ]
        return items[kwargs.get("offset", 0) : kwargs.get("offset", 0) + kwargs.get("limit", 100)]

    async def get_accessible(self, user_id, collection_id):
        collection = self.store.collections.get(collection_id)
        if collection and collection.owner_id == user_id:
            return collection
        return None


class FakeAccessService:
    """Owners may do everything; nobody else has access."""

    def __init__(self, store: Store):
        self.store = store

    async def can_write(self, user_id, collection):
        return collection.owner_id == user_id

    async def can_delete(self, user_id, collection):
        return collection.owner_id == user_id

    async def check_org_can_create_collection(self, user_id, organization_id):
        return False
