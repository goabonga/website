# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Search service for semantic similarity search."""

from uuid import UUID

from sqlalchemy import literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.config import get_settings
from knowledge.models.collection import Collection
from knowledge.models.document import Document
from knowledge.schemas.search import SearchRequest, SearchResponse, SearchResult
from knowledge.services.collections import CollectionService
from knowledge.services.embeddings import get_embedding_service

settings = get_settings()

# pgvector distance operators and their similarity conversions
DISTANCE_CONFIG = {
    "cosine": {
        "operator": "<=>",
        # Cosine distance is 0-2, similarity = 1 - distance
        "similarity_expr": "1 - (documents.embedding <=> :query_embedding)",
        "threshold_expr": "1 - (documents.embedding <=> :query_embedding) >= :threshold",
    },
    "l2": {
        "operator": "<->",
        # L2 distance is 0-inf, convert to similarity: 1 / (1 + distance)
        "similarity_expr": "1.0 / (1.0 + (documents.embedding <-> :query_embedding))",
        "threshold_expr": "1.0 / (1.0 + (documents.embedding <-> :query_embedding)) >= :threshold",
    },
    "inner_product": {
        "operator": "<#>",
        # Inner product returns negative value, negate for similarity
        # Note: vectors should be normalized for meaningful results
        "similarity_expr": "-(documents.embedding <#> :query_embedding)",
        "threshold_expr": "-(documents.embedding <#> :query_embedding) >= :threshold",
    },
}


class SearchService:
    """Service for semantic search across documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.embedding_service = get_embedding_service()
        self.collection_service = CollectionService(db)

    async def search(
        self,
        tenant_id: UUID,
        request: SearchRequest,
    ) -> SearchResponse:
        """Perform semantic search across collections.

        Args:
            tenant_id: The tenant ID.
            request: Search request parameters.

        Returns:
            Search response with results.
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_text(request.query)

        # Resolve collection IDs
        collection_ids: list[UUID] = []
        if request.collection_ids:
            for id_or_slug in request.collection_ids:
                collection = await self.collection_service.get_by_id_or_slug(tenant_id, id_or_slug)
                if collection:
                    collection_ids.append(collection.id)
        else:
            # Search all tenant collections
            collections = await self.collection_service.list(tenant_id)
            collection_ids = [c.id for c in collections]

        if not collection_ids:
            return SearchResponse(results=[], query=request.query, total_results=0)

        # Build the similarity search query using configured distance type
        distance_config = DISTANCE_CONFIG[request.distance_type]

        # Format the embedding as a PostgreSQL vector literal
        embedding_literal = f"'{query_embedding}'::vector"

        # Build SQL expressions with the literal embedding
        similarity_sql = distance_config["similarity_expr"].replace(
            ":query_embedding", embedding_literal
        )
        threshold_sql = distance_config["threshold_expr"].replace(
            ":query_embedding", embedding_literal
        )

        query = (
            select(
                Document.id,
                Document.collection_id,
                Document.content,
                Document.doc_metadata,
                Document.source_type,
                Document.source_ref,
                Document.created_at,
                Collection.slug.label("collection_slug"),
                literal_column(similarity_sql).label("score"),
            )
            .join(Collection, Document.collection_id == Collection.id)
            .where(
                Document.collection_id.in_(collection_ids),
                text(threshold_sql.replace(":threshold", str(request.threshold))),
            )
            .order_by(text("score DESC"))
            .limit(request.top_k)
        )

        result = await self.db.execute(query)

        rows = result.all()

        results = [
            SearchResult(
                document_id=row.id,
                collection_id=row.collection_id,
                collection_slug=row.collection_slug,
                content=row.content if request.include_content else "",
                score=float(row.score),
                metadata=row.doc_metadata,
            )
            for row in rows
        ]

        return SearchResponse(
            results=results,
            query=request.query,
            total_results=len(results),
        )

    async def search_collection(
        self,
        tenant_id: UUID,
        collection_id_or_slug: str,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search within a specific collection.

        Args:
            tenant_id: The tenant ID.
            collection_id_or_slug: Collection ID or slug.
            query: Search query.
            top_k: Maximum results.
            threshold: Minimum similarity threshold.
            filters: Optional metadata filters.

        Returns:
            List of search results.
        """
        request = SearchRequest(
            query=query,
            collection_ids=[collection_id_or_slug],
            top_k=top_k,
            threshold=threshold,
            filters=filters,
        )
        response = await self.search(tenant_id, request)
        return response.results
