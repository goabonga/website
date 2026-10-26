# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the knowledge base feature."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.knowledge import KnowledgeNamespace
from backend.rag.knowledge_base import KnowledgeBase
from behave import given, then, when


def _scopes(text):
    return {scope.strip() for scope in text.split(",") if scope.strip()}


def _namespace(slug, public, scopes):
    return KnowledgeNamespace(
        id=1, slug=slug, name=slug, is_public=public, required_scopes=scopes or None
    )


@given('a namespace "{slug}" that is public and requires no scope')
def step_public(context, slug):
    context.namespace = _namespace(slug, True, None)


@given('a namespace "{slug}" that is private and requires no scope')
def step_private(context, slug):
    context.namespace = _namespace(slug, False, None)


@given('a namespace "{slug}" that is public and requires the scopes "{scopes}"')
def step_scoped(context, slug, scopes):
    context.namespace = _namespace(slug, True, sorted(_scopes(scopes)))


@given('a namespace "{slug}" that is private and requires the scopes "{scopes}"')
def step_private_scoped(context, slug, scopes):
    context.namespace = _namespace(slug, False, sorted(_scopes(scopes)))


@then("the namespace should be accessible to an anonymous user")
def step_accessible_anonymous(context):
    assert context.namespace.is_accessible(None) is True


@then("the namespace should not be accessible to an anonymous user")
def step_not_accessible_anonymous(context):
    assert context.namespace.is_accessible(None) is False


@then('the namespace should be accessible with the scopes "{scopes}"')
def step_accessible_with(context, scopes):
    assert context.namespace.is_accessible(_scopes(scopes)) is True


@then('the namespace should not be accessible with the scopes "{scopes}"')
def step_not_accessible_with(context, scopes):
    assert context.namespace.is_accessible(_scopes(scopes)) is False


def _install_embeddings(context):
    patcher = patch("backend.rag.knowledge_base.EmbeddingService")
    service_cls = patcher.start()
    context.patches["embeddings"] = patcher
    context.embedding_service = service_cls.return_value
    context.embedding_service.generate = AsyncMock(return_value=[0.1] * 1536)


def _namespaces_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


@given("the database holds the entries:")
def step_entries(context):
    _install_embeddings(context)
    rows = [
        SimpleNamespace(
            id=int(row["id"]),
            question=row["question"],
            answer=row["answer"],
            metadata={},
            namespace_id=None,
            namespace_slug=None,
            namespace_name=None,
            similarity=row["similarity"],
        )
        for row in context.table
    ]
    search_result = MagicMock()
    search_result.fetchall.return_value = rows
    context.db.execute.side_effect = [_namespaces_result(), search_result]


@given("the database holds no matching entry")
def step_no_entries(context):
    _install_embeddings(context)
    search_result = MagicMock()
    search_result.fetchall.return_value = []
    context.db.execute.side_effect = [_namespaces_result(), search_result]


@when('I search the knowledge base for "{query}"')
def step_search(context, query):
    knowledge_base = KnowledgeBase(context.db)
    context.query = query
    context.results = asyncio.run(knowledge_base.search(query))


@then("the search should return {count:d} results")
def step_result_count(context, count):
    assert len(context.results) == count, context.results


@then("the first result should be entry {entry_id:d} with the similarity {similarity:f}")
def step_first_result(context, entry_id, similarity):
    first = context.results[0]
    assert first["id"] == entry_id
    assert first["similarity"] == similarity
    assert first["namespace"] is None


@then("the query should have been embedded")
def step_embedded(context):
    context.embedding_service.generate.assert_awaited_once_with(context.query)
