# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the search page.

The page, its parameters and its template are real. The pgvector ranking is
replaced by the in-memory cosine search used by the API scenarios.
"""

from unittest.mock import patch

from behave import given, when
from fakes import FakeSearchService


@given("the web search is in memory")
def step_web_search(context):
    patcher = patch(
        "knowledge.routes.web.search.SearchService",
        lambda db: FakeSearchService(context.store, context.embedder),
    )
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("the search backend is failing")
def step_search_failing(context):
    class Failing:
        def __init__(self, db):
            pass

        async def search(self, tenant_id, request):
            raise RuntimeError("vector index unavailable")

    patcher = patch("knowledge.routes.web.search.SearchService", Failing)
    patcher.start()
    context.add_cleanup(patcher.stop)


@when('I submit the search form for "{query}" in the collections "{first}" and "{second}"')
def step_submit_search(context, query, first, second):
    context.response = context.call(
        "POST",
        "/search",
        data={"query": query, "collection_ids_list": [first, second]},
        follow_redirects=False,
    )
