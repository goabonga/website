# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-memory fakes used by the behave scenarios.

The routes are exercised for real (routing, validation, scope checks,
serialization). Only the persistence layer is replaced by small in-memory
stand-ins so that no database is needed.
"""

import hashlib
import math
import operator
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from sqlalchemy import inspect
from sqlalchemy.sql import functions as sql_functions
from sqlalchemy.sql.elements import False_, True_
from sqlalchemy.sql.operators import desc_op, in_op

from knowledge.auth.dependencies import AuthContext
from knowledge.auth.models import User
from knowledge.models import (
    Collection,
    CollectionCollaborator,
    CollectionInvitation,
    Document,
    McpRelease,
    McpReleaseAsset,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
)
from knowledge.models.enums import CollaboratorPermission, OwnerType
from knowledge.schemas.search import SearchResponse, SearchResult
from knowledge.services.collaborators import CollaboratorService
from knowledge.services.collection_invitations import CollectionInvitationService
from knowledge.services.documents import DocumentService

COMPARISONS = {
    operator.gt: operator.gt,
    operator.lt: operator.lt,
    operator.ge: operator.ge,
    operator.le: operator.le,
}


class Store:
    """Shared in-memory state of one scenario."""

    def __init__(self):
        self.collections: dict[UUID, Collection] = {}
        self.documents: dict[UUID, Document] = {}
        self.collaborators: dict[UUID, CollectionCollaborator] = {}
        self.invitations: dict[UUID, CollectionInvitation] = {}
        self.releases: dict[UUID, McpRelease] = {}
        self.release_assets: dict[UUID, McpReleaseAsset] = {}
        self.organizations: dict[UUID, Organization] = {}
        self.members: dict[UUID, OrganizationMember] = {}
        self.org_invitations: dict[UUID, OrganizationInvitation] = {}

    def tables(self):
        """In-memory tables by SQL table name."""
        return {
            "collections": self.collections,
            "documents": self.documents,
            "collection_collaborators": self.collaborators,
            "collection_invitations": self.invitations,
            "mcp_releases": self.releases,
            "mcp_release_assets": self.release_assets,
            "tenants": self.organizations,
            "tenant_members": self.members,
            "invitations": self.org_invitations,
        }

    def bucket_for(self, obj):
        """Return the in-memory table holding objects of this type, if any."""
        for cls, bucket in (
            (Collection, self.collections),
            (Document, self.documents),
            (CollectionCollaborator, self.collaborators),
            (CollectionInvitation, self.invitations),
            (McpRelease, self.releases),
            (McpReleaseAsset, self.release_assets),
            (Organization, self.organizations),
            (OrganizationMember, self.members),
            (OrganizationInvitation, self.org_invitations),
        ):
            if isinstance(obj, cls):
                return bucket
        return None


def _attribute_name(obj, column) -> str:
    """Mapped attribute holding a column (a column key can differ from its attribute)."""
    return inspect(type(obj)).get_property_by_column(column).key


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

    def _add(self, obj):
        bucket = self.store.bucket_for(obj)
        if bucket is not None:
            apply_flush_defaults(obj)
            bucket[obj.id] = obj
            if isinstance(obj, McpReleaseAsset):
                self.store.releases[obj.release_id].assets.append(obj)

    async def execute(self, statement):
        """Evaluate simple SELECTs (and COUNTs) over the in-memory tables.

        Supported: equality, inequality and IN filters on columns of the queried table,
        filters on the owning collection for documents, descending ordering, offset and
        limit. A statement that needs anything else (other joins) answers no row.
        """
        rows, count = self._evaluate(statement)
        result = MagicMock()
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        result.scalar.return_value = count
        result.scalars.return_value.all.return_value = rows
        result.all.return_value = []
        return result

    def _evaluate(self, statement):
        if not hasattr(statement, "column_descriptions"):
            return [], 0
        expr = statement.column_descriptions[0].get("expr")
        is_count = isinstance(expr, sql_functions.count)
        if is_count:
            table_name = list(expr.clauses)[0].table.name
        else:
            entity = statement.column_descriptions[0].get("entity")
            if entity is None or not hasattr(entity, "__table__"):
                return [], 0
            table_name = entity.__table__.name
        bucket = self.store.tables().get(table_name)
        if bucket is None:
            return [], 0
        rows = list(bucket.values())
        for criterion in statement._where_criteria:
            rows = self._filter(rows, table_name, criterion)
            if rows is None:
                return [], 0
        if is_count:
            return rows, len(rows)
        for clause in statement._order_by_clauses[:1]:
            key = getattr(clause, "element", clause).key
            descending = getattr(clause, "modifier", None) is desc_op
            rows.sort(
                key=lambda r: (getattr(r, key) is not None, getattr(r, key)), reverse=descending
            )
        if statement._offset_clause is not None:
            rows = rows[statement._offset_clause.value :]
        if statement._limit_clause is not None:
            rows = rows[: statement._limit_clause.value]
        return rows, 0

    def _filter(self, rows, table_name, criterion):
        column, op = criterion.left, criterion.operator
        right = criterion.right
        if isinstance(right, True_):
            expected = True
        elif isinstance(right, False_):
            expected = False
        else:
            expected = right.value
        if column.table.name == table_name:

            def current(row):
                return getattr(row, _attribute_name(row, column))
        elif table_name == "documents" and column.table.name == "collections":

            def current(row):
                collection = self.store.collections.get(row.collection_id)
                return getattr(collection, _attribute_name(collection, column), None)
        else:
            return None
        if op is operator.eq:
            return [r for r in rows if current(r) == expected]
        if op is operator.ne:
            return [r for r in rows if current(r) != expected]
        if op is in_op:
            return [r for r in rows if current(r) in expected]
        if op in COMPARISONS:
            compare = COMPARISONS[op]
            return [r for r in rows if compare(current(r), expected)]
        raise NotImplementedError(f"unsupported operator {op}")

    async def delete(self, obj):
        bucket = self.store.bucket_for(obj)
        if bucket is not None:
            bucket.pop(obj.id, None)
        if isinstance(obj, Collection):
            for table in (self.store.documents, self.store.collaborators, self.store.invitations):
                for key in [k for k, v in table.items() if v.collection_id == obj.id]:
                    del table[key]


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


class FakeBillingClient:
    """Configurable stand-in for BillingClient used by the workspace pages."""

    def __init__(self):
        self.is_configured = True
        self.socket_path = ""
        self.api_url = "http://billing.test"
        self.plans = []
        self.subscription = None
        self.preview = None
        self.upgrade_result = None
        self.error = None
        self.checkout_calls = []
        self.upgrade_calls = []
        self.cancel_calls = []
        self.reactivate_calls = []

    def _raise(self):
        if self.error is not None:
            raise self.error

    async def get_plans(self):
        self._raise()
        return self.plans

    async def get_tenant_subscription(self, tenant_id):
        self._raise()
        return self.subscription

    async def create_checkout_session(self, **kwargs):
        self._raise()
        self.checkout_calls.append(kwargs)
        return SimpleNamespace(session_id="cs_1", url="https://checkout.example.test/session")

    async def preview_upgrade(self, **kwargs):
        self._raise()
        return self.preview

    async def upgrade_subscription(self, **kwargs):
        self._raise()
        self.upgrade_calls.append(kwargs)
        return self.upgrade_result

    async def cancel_subscription(self, *args, **kwargs):
        self._raise()
        self.cancel_calls.append((args, kwargs))
        return SimpleNamespace(success=True, cancel_at=None)

    async def reactivate_subscription(self, *args, **kwargs):
        self._raise()
        self.reactivate_calls.append((args, kwargs))
        return SimpleNamespace(success=True)
