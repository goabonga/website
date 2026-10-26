# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the search page in a browser.

PostgreSQL ranks the documents with the pgvector operators, which SQLite does not have: the
search page is served here by a ranking done in Python with the same contract as
``SearchService``. The query and the documents are embedded by the bag-of-words model of the
stack, so words in common mean similarity.
"""

import math
from unittest.mock import patch

import browser_stack
from sqlalchemy import select

from knowledge.models import Document
from knowledge.schemas.search import SearchRequest, SearchResponse, SearchResult
from knowledge.services.collections import CollectionService


def cosine(a, b) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


class MemorySearchService:
    """``SearchService`` for SQLite: the same contract, the ranking done in Python."""

    def __init__(self, db, embedder):
        self.db = db
        self.embedder = embedder
        self.collections = CollectionService(db)

    async def search(self, tenant_id, request: SearchRequest) -> SearchResponse:
        query = await self.embedder.embed_text(request.query)
        if request.collection_ids:
            found = [
                await self.collections.get_by_id_or_slug(tenant_id, key)
                for key in request.collection_ids
            ]
            collections = [c for c in found if c is not None]
        else:
            collections = await self.collections.list(tenant_id)
        slugs = {c.id: c.slug for c in collections}
        rows = (
            (await self.db.execute(select(Document).where(Document.collection_id.in_(slugs))))
            .scalars()
            .all()
        )
        scored = sorted(
            ((cosine(query, list(row.embedding)), row) for row in rows),
            key=lambda item: item[0],
            reverse=True,
        )
        results = [
            SearchResult(
                document_id=row.id,
                collection_id=row.collection_id,
                collection_slug=slugs[row.collection_id],
                content=row.content if request.include_content else "",
                score=score,
                metadata=row.doc_metadata,
            )
            for score, row in scored
            if score >= request.threshold
        ][: request.top_k]
        return SearchResponse(results=results, query=request.query, total_results=len(results))


@browser_stack.scenario_setup
def install_search_service(stack, scenario):
    scenario.enter_context(
        patch(
            "knowledge.routes.web.search.SearchService",
            lambda db: MemorySearchService(db, stack.embedder),
        )
    )
