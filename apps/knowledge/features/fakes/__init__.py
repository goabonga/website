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
from knowledge.models import Collection, Document
from knowledge.models.enums import OwnerType
from knowledge.services.documents import DocumentService


class Store:
    """Shared in-memory state of one scenario."""

    def __init__(self):
        self.collections: dict[UUID, Collection] = {}
        self.documents: dict[UUID, Document] = {}


class FakeSession:
    """Minimal AsyncSession stand-in: flush/refresh are no-ops, delete removes from the store."""

    def __init__(self, store: Store):
        self.store = store
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.add = MagicMock(side_effect=self._add)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        self.execute = AsyncMock(return_value=result)

    def _add(self, obj):
        if isinstance(obj, Document):
            now = datetime.now(UTC)
            obj.id = obj.id or uuid4()
            obj.created_at = now
            obj.updated_at = now
            self.store.documents[obj.id] = obj

    async def delete(self, obj):
        self.store.collections.pop(obj.id, None)
        self.store.documents.pop(obj.id, None)


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


class FakeTenantCollectionService:
    """Tenant-scoped lookups used by the document routes."""

    def __init__(self, store: Store):
        self.store = store

    async def get_by_id_or_slug(self, tenant_id, id_or_slug):
        for collection in self.store.collections.values():
            if collection.organization_id == tenant_id and id_or_slug in (
                str(collection.id),
                collection.slug,
            ):
                return collection
        return None

    async def get_by_id(self, tenant_id, collection_id):
        collection = self.store.collections.get(collection_id)
        if collection and collection.organization_id == tenant_id:
            return collection
        return None


class FakeEmbeddingService:
    """Deterministic embedder that records what it was asked to embed."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.calls: list[list[str]] = []

    async def embed_text(self, text):
        self.calls.append([text])
        return [0.1] * self.dimension

    async def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [[0.1] * self.dimension for _ in texts]


class FakeDocumentService(DocumentService):
    """Real DocumentService (hashing, sizing, embedding) over an in-memory store."""

    store: Store

    async def get_by_id(self, document_id, collection_id=None):
        document = self.db.store.documents.get(document_id)
        if document and (collection_id is None or document.collection_id == collection_id):
            return document
        return None

    async def list(self, collection_id, offset=0, limit=100):
        items = [d for d in self.db.store.documents.values() if d.collection_id == collection_id]
        return items[offset : offset + limit]
