# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-memory fakes used by the behave scenarios.

The routes are exercised for real (routing, validation, scope checks,
serialization). Only the persistence layer is replaced by small in-memory
stand-ins so that no database is needed.
"""

import hashlib
import math
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from sqlalchemy import inspect

from knowledge.auth.dependencies import AuthContext
from knowledge.auth.models import User
from knowledge.models import Collection, CollectionCollaborator, CollectionInvitation, Document
from knowledge.models.enums import CollaboratorPermission, OwnerType
from knowledge.schemas.search import SearchResponse, SearchResult
from knowledge.services.collaborators import CollaboratorService
from knowledge.services.collection_invitations import CollectionInvitationService
from knowledge.services.documents import DocumentService


class Store:
    """Shared in-memory state of one scenario."""

    def __init__(self):
        self.collections: dict[UUID, Collection] = {}
        self.documents: dict[UUID, Document] = {}
        self.collaborators: dict[UUID, CollectionCollaborator] = {}
        self.invitations: dict[UUID, CollectionInvitation] = {}

    def bucket_for(self, obj):
        """Return the in-memory table holding objects of this type, if any."""
        for cls, bucket in (
            (Collection, self.collections),
            (Document, self.documents),
            (CollectionCollaborator, self.collaborators),
            (CollectionInvitation, self.invitations),
        ):
            if isinstance(obj, cls):
                return bucket
        return None


def apply_flush_defaults(obj):
    """Mimic what a flush does: Python-side column defaults and server timestamps."""
    now = datetime.now(UTC)
    for attr in inspect(type(obj)).column_attrs:
        if getattr(obj, attr.key) is not None:
            continue
        column = attr.columns[0]
        default = column.default
        if default is not None and default.is_scalar:
            setattr(obj, attr.key, default.arg)
        elif default is not None and default.is_callable:
            setattr(obj, attr.key, default.arg(None))
        elif column.server_default is not None and attr.key in ("created_at", "updated_at"):
            setattr(obj, attr.key, now)


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
        bucket = self.store.bucket_for(obj)
        if bucket is not None:
            apply_flush_defaults(obj)
            bucket[obj.id] = obj

    async def delete(self, obj):
        bucket = self.store.bucket_for(obj)
        if bucket is not None:
            bucket.pop(obj.id, None)


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
        if collection is None:
            return None
        if collection.owner_id == user_id:
            return collection
        if any(
            c.collection_id == collection_id and c.user_id == user_id
            for c in self.store.collaborators.values()
        ):
            return collection
        return None

    async def get_by_id_global(self, collection_id):
        return self.store.collections.get(collection_id)


class FakeAccessService:
    """Owners may do everything; collaborators get what their permission grants."""

    LEVELS = {
        CollaboratorPermission.READ: 1,
        CollaboratorPermission.WRITE: 2,
        CollaboratorPermission.ADMIN: 3,
    }

    def __init__(self, store: Store):
        self.store = store

    def _level(self, user_id, collection) -> int:
        if collection.owner_id == user_id:
            return 4
        for collaborator in self.store.collaborators.values():
            if collaborator.collection_id == collection.id and collaborator.user_id == user_id:
                return self.LEVELS[collaborator.permission]
        return 0

    async def can_read(self, user_id, collection):
        return self._level(user_id, collection) >= 1

    async def can_write(self, user_id, collection):
        return self._level(user_id, collection) >= 2

    async def can_admin(self, user_id, collection):
        return self._level(user_id, collection) >= 3

    async def can_invite(self, user_id, collection):
        return self._level(user_id, collection) >= 3

    async def can_delete(self, user_id, collection):
        return self._level(user_id, collection) >= 4

    async def check_org_can_create_collection(self, user_id, organization_id):
        return False


class FakeCollaboratorService(CollaboratorService):
    """Real CollaboratorService logic; only the two read queries are in memory."""

    async def list(self, collection_id, offset=0, limit=100):
        items = [
            c for c in self.db.store.collaborators.values() if c.collection_id == collection_id
        ]
        return items[offset : offset + limit]

    async def get(self, collection_id, user_id):
        for collaborator in self.db.store.collaborators.values():
            if collaborator.collection_id == collection_id and collaborator.user_id == user_id:
                return collaborator
        return None


class FakeInvitationService(CollectionInvitationService):
    """Real CollectionInvitationService logic; only the read queries are in memory."""

    async def get_by_id(self, invitation_id):
        return self.db.store.invitations.get(invitation_id)

    async def get_by_token(self, token):
        for invitation in self.db.store.invitations.values():
            if invitation.token == token:
                return invitation
        return None

    async def get_pending_for_email(self, collection_id, email):
        for invitation in self.db.store.invitations.values():
            if (
                invitation.collection_id == collection_id
                and invitation.email == email.lower()
                and invitation.is_pending
            ):
                return invitation
        return None

    async def list_for_collection(self, collection_id, status=None, offset=0, limit=100):
        items = [
            i
            for i in self.db.store.invitations.values()
            if i.collection_id == collection_id and (status is None or i.status == status)
        ]
        return items[offset : offset + limit]


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

    async def list(self, tenant_id, offset=0, limit=100):
        return [c for c in self.store.collections.values() if c.organization_id == tenant_id]


class FakeEmbeddingService:
    """Deterministic embedder that records what it was asked to embed."""

    def __init__(self, dimension: int = 1536, vectorizer=None):
        self.dimension = dimension
        self.vectorizer = vectorizer or (lambda text: [0.1] * self.dimension)
        self.calls: list[list[str]] = []

    async def embed_text(self, text):
        self.calls.append([text])
        return self.vectorizer(text)

    async def embed_texts(self, texts):
        self.calls.append(list(texts))
        return [self.vectorizer(text) for text in texts]


def hashing_vectorizer(text: str, dimension: int = 1024) -> list[float]:
    """Bag-of-words embedding: words are hashed into buckets, so shared words mean similarity."""
    vector = [0.0] * dimension
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % dimension
        vector[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class FakeSearchService:
    """In-memory cosine search with the same contract as SearchService.search."""

    def __init__(self, store: Store, embedder):
        self.store = store
        self.embedder = embedder
        self.collections = FakeTenantCollectionService(store)

    async def search(self, tenant_id, request):
        query_embedding = await self.embedder.embed_text(request.query)
        collection_ids = []
        if request.collection_ids:
            for id_or_slug in request.collection_ids:
                collection = await self.collections.get_by_id_or_slug(tenant_id, id_or_slug)
                if collection:
                    collection_ids.append(collection.id)
        else:
            collection_ids = [c.id for c in await self.collections.list(tenant_id)]

        scored = []
        for document in self.store.documents.values():
            if document.collection_id not in collection_ids:
                continue
            score = cosine(query_embedding, document.embedding)
            if score >= request.threshold:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)

        results = [
            SearchResult(
                document_id=document.id,
                collection_id=document.collection_id,
                collection_slug=self.store.collections[document.collection_id].slug,
                content=document.content if request.include_content else "",
                score=score,
                metadata=document.doc_metadata,
            )
            for score, document in scored[: request.top_k]
        ]
        return SearchResponse(results=results, query=request.query, total_results=len(results))


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
