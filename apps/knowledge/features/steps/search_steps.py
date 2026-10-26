# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the semantic search feature.

The pgvector ranking is replaced by an in-memory cosine similarity over a
bag-of-words embedding; the route, the request validation, the collection
resolution and the response shape are the real ones.
"""

from unittest.mock import patch

from behave import given
from fakes import FakeSearchService, hashing_vectorizer


@given("the embedder is keyword based")
def step_keyword_embedder(context):
    context.embedder.vectorizer = hashing_vectorizer


@given("the search data layer is in memory")
def step_search_in_memory(context):
    patcher = patch(
        "knowledge.routes.search.SearchService",
        lambda db: FakeSearchService(context.store, context.embedder),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)
