# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the documents feature."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from behave import given, then, when
from fakes import FakeDocumentService, FakeEmbeddingService, FakeTenantCollectionService

from knowledge.models import Collection
from knowledge.models.enums import OwnerType
from knowledge.schemas.document import DocumentCreate


@given("the documents data layer is in memory")
def step_documents_in_memory(context):
    store = context.store
    context.embedder = FakeEmbeddingService()
    for target, fake in (
        (
            "knowledge.routes.documents.CollectionService",
            lambda db: FakeTenantCollectionService(store),
        ),
        ("knowledge.routes.documents.DocumentService", FakeDocumentService),
        ("knowledge.services.documents.CollectionService", lambda db: _NoCountService()),
        ("knowledge.services.documents.get_embedding_service", lambda: context.embedder),
    ):
        patcher = patch(target, fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


class _NoCountService:
    """The document counter lives in the database: nothing to do in memory."""

    async def increment_document_count(self, collection_id, increment=1):
        return None


@given('a collection "{name}" with slug "{slug}" in my tenant')
def step_tenant_collection(context, name, slug):
    tenant = UUID(context.tenant_id)
    now = datetime.now(UTC)
    collection = Collection(
        id=uuid4(),
        owner_type=OwnerType.ORGANIZATION,
        owner_id=tenant,
        organization_id=tenant,
        name=name,
        slug=slug,
        embedding_model="text-embedding-3-small",
        dimension=1536,
        document_count=0,
        created_at=now,
        updated_at=now,
    )
    context.store.collections[collection.id] = collection


def _collection(context, slug):
    return next(c for c in context.store.collections.values() if c.slug == slug)


@given('a document "{content}" in the collection "{slug}"')
def step_existing_document(context, content, slug):
    service = FakeDocumentService(context.session)
    asyncio.run(service.create(_collection(context, slug).id, DocumentCreate(content=content)))
    context.embedder.calls.clear()


def _document(context, content):
    return next(d for d in context.store.documents.values() if d.content == content)


@when('I get the document "{content}"')
def step_get_document(context, content):
    try:
        document_id = _document(context, content).id
    except StopIteration:
        document_id = uuid4()
    context.response = context.call("GET", f"/api/v1/documents/{document_id}")
    context.last_document = content


@when('I delete the document "{content}" from the collection "{slug}"')
def step_delete_document(context, content, slug):
    context.deleted_id = _document(context, content).id
    context.response = context.call(
        "DELETE", f"/api/v1/collections/{slug}/documents/{context.deleted_id}"
    )


@then('the text "{text}" should have been embedded')
def step_text_embedded(context, text):
    assert [text] in context.embedder.calls, context.embedder.calls


@then("the embedder should have received one batch of {count:d} texts")
def step_one_batch(context, count):
    assert len(context.embedder.calls) == 1 and len(context.embedder.calls[0]) == count, (
        context.embedder.calls
    )
