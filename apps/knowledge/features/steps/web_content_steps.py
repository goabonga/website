# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the collection and document pages.

Templates, routes and the document service are real. The database is the
in-memory store, embeddings come from a deterministic fake and the quota
service is a fake that can be told to refuse.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from behave import given, then, when
from fakes import FakeDocumentService, FakeEmbeddingService, FakeSession, Store

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.models import Collection, Organization, OrganizationMember
from knowledge.models.enums import OrganizationMemberRole, OwnerType, PlanType
from knowledge.schemas.document import DocumentCreate
from knowledge.services.quotas import QuotaExceededError


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


class _Quota:
    """Quota service that refuses when the scenario asks for it."""

    refuse_collections = False
    refuse_documents = False

    def __init__(self, db):
        pass

    async def enforce_collection_quota(self, tenant):
        if _Quota.refuse_collections:
            raise QuotaExceededError("max_collections", 3, 3)

    async def enforce_document_quota(self, tenant, collection_id):
        if _Quota.refuse_documents:
            raise QuotaExceededError("max_total_documents", 200, 200)

    async def enforce_storage_quota(self, tenant):
        return None


class _NoCount:
    async def increment_document_count(self, collection_id, increment=1):
        return None


@given('I am a member of the workspace "{name}" on the "{plan}" plan')
def step_member(context, name, plan):
    _Quota.refuse_collections = False
    _Quota.refuse_documents = False
    context.tenant = Organization(id=uuid4(), name=name, slug=name.lower(), plan=PlanType(plan))
    user = User(id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), name="Alice")
    member = OrganizationMember(
        organization_id=context.tenant.id, user_id=user.id, role=OrganizationMemberRole.OWNER
    )
    context.internal_app.dependency_overrides[get_web_auth_context] = lambda: WebAuthContext(
        user=user, tenant=context.tenant, tenant_member=member
    )


@given("I am not signed in")
def step_not_signed_in(context):
    context.internal_app.dependency_overrides.pop(get_web_auth_context, None)


@given("the content pages database is in memory")
def step_content_database(context):
    context.store = Store()
    context.session = FakeSession(context.store)

    async def fake_db():
        yield context.session

    context.internal_app.dependency_overrides[get_db] = fake_db


@given("the content services are in memory")
def step_content_services(context):
    context.embedder = FakeEmbeddingService()
    _patch(context, "knowledge.services.documents.get_embedding_service", lambda: context.embedder)
    _patch(
        context, "knowledge.routes.web.documents.get_embedding_service", lambda: context.embedder
    )
    _patch(context, "knowledge.services.documents.CollectionService", lambda db: _NoCount())
    _patch(context, "knowledge.routes.web.collections.QuotaService", _Quota)
    _patch(context, "knowledge.routes.web.documents.QuotaService", _Quota)


@given("the plan allows no more collections")
def step_no_more_collections(context):
    _Quota.refuse_collections = True


@given("the plan allows no more documents")
def step_no_more_documents(context):
    _Quota.refuse_documents = True


def _new_collection(context, name, tenant):
    now = datetime.now(UTC)
    collection = Collection(
        id=uuid4(),
        owner_type=OwnerType.ORGANIZATION,
        owner_id=tenant.id,
        organization_id=tenant.id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        embedding_model="text-embedding-3-small",
        dimension=1536,
        document_count=0,
        created_at=now,
        updated_at=now,
    )
    context.store.collections[collection.id] = collection
    return collection


@given('the workspace has a collection "{name}"')
def step_workspace_collection(context, name):
    _new_collection(context, name, context.tenant)


@given('another workspace has a collection "{name}"')
def step_other_collection(context, name):
    _new_collection(context, name, Organization(id=uuid4(), name="Other", slug="other"))


def _collection(context, name):
    return next(c for c in context.store.collections.values() if c.name == name)


def _document(context, content):
    return next(d for d in context.store.documents.values() if d.content == content)


@given('the collection "{name}" holds the document "{content}"')
def step_collection_document(context, name, content):
    service = FakeDocumentService(context.session)
    asyncio.run(service.create(_collection(context, name).id, DocumentCreate(content=content)))
    context.embedder.calls.clear()


def _post(context, path, **kwargs):
    context.response = context.call("POST", path, follow_redirects=False, **kwargs)


# --- collections --------------------------------------------------------------


@when('I create the collection "{name}" with the description "{description}"')
def step_create_collection(context, name, description):
    _post(context, "/collections/new", data={"name": name, "description": description})


@when('I try to create the collection "{name}"')
def step_try_create_collection(context, name):
    _post(context, "/collections/new", data={"name": name})


@when('I open the page of the collection "{name}"')
def step_open_collection(context, name):
    context.response = context.call(
        "GET", f"/collections/{_collection(context, name).id}", follow_redirects=False
    )


@when('I rename the collection "{name}" to "{new_name}"')
def step_rename_collection(context, name, new_name):
    _post(context, f"/collections/{_collection(context, name).id}/edit", data={"name": new_name})


@when('I remove the collection "{name}" from the workspace')
def step_delete_collection(context, name):
    _post(context, f"/collections/{_collection(context, name).id}/delete")


@when('I delete the document "{content}" from the page of the collection "{name}"')
def step_delete_selected(context, content, name):
    _post(
        context,
        f"/collections/{_collection(context, name).id}/documents/delete",
        data={"document_ids": str(_document(context, content).id)},
    )


@then('the page should not say "{text}"')
def step_page_not_says(context, text):
    assert text not in context.response.text


@then('the workspace should own a collection with slug "{slug}"')
def step_owns_slug(context, slug):
    owned = [
        c for c in context.store.collections.values() if c.organization_id == context.tenant.id
    ]
    assert slug in [c.slug for c in owned], [c.slug for c in owned]


@then('the workspace should not own a collection with slug "{slug}"')
def step_not_owns_slug(context, slug):
    assert slug not in [c.slug for c in context.store.collections.values()]


@then('I should be redirected to the page of the collection "{slug}"')
def step_redirected_to_collection(context, slug):
    collection = next(c for c in context.store.collections.values() if c.slug == slug)
    assert context.response.headers["location"] == f"/collections/{collection.id}"


@then('the workspace should have a collection named "{name}"')
def step_has_named_collection(context, name):
    assert name in [c.name for c in context.store.collections.values()]


@then("the workspace should have {count:d} collections")
def step_collection_count(context, count):
    assert len(context.store.collections) == count


@then("the workspace should have {count:d} documents")
def step_document_count(context, count):
    assert len(context.store.documents) == count


# --- documents ------------------------------------------------------------------


@when('I add the text "{text}" to the collection "{name}"')
def step_add_text(context, text, name):
    _post(context, f"/documents/{_collection(context, name).id}/new", data={"content": text})


@when(
    'I add a markdown text with {sections:d} sections to the collection "{name}" split by sections'
)
def step_add_markdown(context, sections, name):
    text = "\n\n".join(f"# Section {i}\nBody {i}" for i in range(1, sections + 1))
    _post(
        context,
        f"/documents/{_collection(context, name).id}/new",
        data={"content": text, "enable_chunking": "true", "chunk_mode": "markdown_sections"},
    )


@when('I upload the file "{filename}" containing "{content}" to the collection "{name}"')
def step_upload(context, filename, content, name):
    _post(
        context,
        f"/documents/{_collection(context, name).id}/new",
        files={"file": (filename, content.encode(), "text/plain")},
    )


@when('I open the page of the document "{content}"')
def step_open_document(context, content):
    context.response = context.call(
        "GET", f"/documents/{_document(context, content).id}", follow_redirects=False
    )


@when('I change the document "{content}" to "{new_content}"')
def step_change_document(context, content, new_content):
    _post(
        context, f"/documents/{_document(context, content).id}/edit", data={"content": new_content}
    )


@when('I remove the document "{content}"')
def step_delete_document(context, content):
    _post(context, f"/documents/{_document(context, content).id}/delete")


@then('the collection "{name}" should hold the documents "{contents}"')
def step_holds_documents(context, name, contents):
    collection_id = _collection(context, name).id
    held = sorted(
        d.content for d in context.store.documents.values() if d.collection_id == collection_id
    )
    assert held == sorted(c.strip() for c in contents.split("|")), held


@then('the collection "{name}" should hold {count:d} documents')
def step_holds_count(context, name, count):
    collection_id = _collection(context, name).id
    assert (
        len([d for d in context.store.documents.values() if d.collection_id == collection_id])
        == count
    )


@then('every document of the collection "{name}" should record its chunking')
def step_chunking(context, name):
    collection_id = _collection(context, name).id
    for document in context.store.documents.values():
        if document.collection_id == collection_id:
            assert document.doc_metadata["chunked"] is True
            assert document.doc_metadata["chunk_mode"] == "markdown_sections"
            assert document.doc_metadata["chunk_count"] == 2


@then('the collection "{name}" should hold a document from the file "{filename}"')
def step_file_document(context, name, filename):
    collection_id = _collection(context, name).id
    sources = [
        (d.source_type, d.source_ref)
        for d in context.store.documents.values()
        if d.collection_id == collection_id
    ]
    assert sources == [("file", filename)], sources
