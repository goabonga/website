# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge base service with semantic search using pgvector."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.logging import get_logger
from backend.models.knowledge import KnowledgeEntry, KnowledgeNamespace
from backend.rag.embeddings import EmbeddingService

logger = get_logger(__name__)


class KnowledgeBase:
    """Knowledge base with semantic search capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.embedding_service = EmbeddingService()

    async def _get_accessible_namespace_ids(
        self,
        user_scopes: set[str] | None = None,
    ) -> list[int] | None:
        """Get list of namespace IDs accessible to the user.

        Args:
            user_scopes: User's scopes (None for anonymous users)

        Returns:
            List of accessible namespace IDs, or None if all are accessible
        """
        stmt = select(KnowledgeNamespace)
        result = await self.session.execute(stmt)
        namespaces = result.scalars().all()

        accessible_ids = []
        for ns in namespaces:
            if ns.is_accessible(user_scopes):
                accessible_ids.append(ns.id)

        return accessible_ids

    async def search(
        self,
        query: str,
        limit: int | None = None,
        threshold: float | None = None,
        user_scopes: set[str] | None = None,
        namespace_slug: str | None = None,
    ) -> list[dict]:
        """
        Search for similar knowledge entries using semantic similarity.

        Args:
            query: The search query
            limit: Maximum number of results (default from settings)
            threshold: Minimum similarity score (default from settings)
            user_scopes: User's scopes for filtering accessible namespaces
            namespace_slug: Optional specific namespace to search in

        Returns:
            List of matching entries with similarity scores
        """
        limit = limit or settings.rag_max_results
        threshold = threshold or settings.rag_similarity_threshold

        logger.debug(
            "RAG search: query='%s', limit=%d, threshold=%.2f, namespace=%s",
            query[:50] + "..." if len(query) > 50 else query,
            limit,
            threshold,
            namespace_slug or "all",
        )

        query_embedding = await self.embedding_service.generate(query)

        # Build the WHERE clause based on namespace access
        where_clauses = [
            "embedding IS NOT NULL",
            "1 - (embedding <=> :embedding) >= :threshold",
        ]
        params: dict = {
            "embedding": str(query_embedding),
            "threshold": threshold,
            "limit": limit,
        }

        # Filter by specific namespace if provided
        if namespace_slug:
            where_clauses.append("""
                namespace_id IN (
                    SELECT id FROM knowledge_namespaces WHERE slug = :namespace_slug
                )
            """)
            params["namespace_slug"] = namespace_slug
        else:
            # Filter by accessible namespaces based on user scopes
            accessible_ids = await self._get_accessible_namespace_ids(user_scopes)
            if accessible_ids:
                # Include entries with NULL namespace (legacy/general) or in accessible namespaces
                where_clauses.append(
                    "(namespace_id IS NULL OR namespace_id = ANY(:accessible_ids))"
                )
                params["accessible_ids"] = accessible_ids
            else:
                # No accessible namespaces, only return entries without namespace
                where_clauses.append("namespace_id IS NULL")

        where_sql = " AND ".join(where_clauses)

        stmt = text(
            f"""
            SELECT
                kb.id,
                kb.question,
                kb.answer,
                kb.metadata,
                kb.namespace_id,
                kn.slug AS namespace_slug,
                kn.name AS namespace_name,
                1 - (kb.embedding <=> :embedding) AS similarity
            FROM knowledge_base kb
            LEFT JOIN knowledge_namespaces kn ON kb.namespace_id = kn.id
            WHERE {where_sql}
            ORDER BY kb.embedding <=> :embedding
            LIMIT :limit
        """
        )

        result = await self.session.execute(stmt, params)

        rows = result.fetchall()
        results = [
            {
                "id": row.id,
                "question": row.question,
                "answer": row.answer,
                "metadata": row.metadata,
                "namespace": {
                    "id": row.namespace_id,
                    "slug": row.namespace_slug,
                    "name": row.namespace_name,
                }
                if row.namespace_id
                else None,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

        if results:
            logger.info(
                "RAG search found %d results (best similarity: %.3f)",
                len(results),
                results[0]["similarity"] if results else 0,
            )
        else:
            logger.debug("RAG search found no results above threshold %.2f", threshold)

        return results

    async def get_namespace_by_slug(self, slug: str) -> KnowledgeNamespace | None:
        """Get a namespace by its slug."""
        stmt = select(KnowledgeNamespace).where(KnowledgeNamespace.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_namespace(
        self,
        slug: str,
        name: str,
        description: str | None = None,
        required_scopes: list[str] | None = None,
        is_public: bool = True,
        metadata: dict | None = None,
    ) -> KnowledgeNamespace:
        """Create a new namespace.

        Args:
            slug: Unique identifier (URL-friendly)
            name: Display name
            description: Optional description
            required_scopes: Scopes required to access this namespace
            is_public: Whether the namespace is publicly accessible
            metadata: Optional metadata dict

        Returns:
            The created KnowledgeNamespace
        """
        namespace = KnowledgeNamespace(
            slug=slug,
            name=name,
            description=description,
            required_scopes=required_scopes,
            is_public=is_public,
            metadata_=metadata or {},
        )

        self.session.add(namespace)
        await self.session.commit()
        await self.session.refresh(namespace)

        logger.info("Created namespace: %s (%s)", namespace.slug, namespace.id)
        return namespace

    async def list_namespaces(
        self,
        user_scopes: set[str] | None = None,
    ) -> list[KnowledgeNamespace]:
        """List all namespaces accessible to the user.

        Args:
            user_scopes: User's scopes for filtering

        Returns:
            List of accessible namespaces
        """
        stmt = select(KnowledgeNamespace).order_by(KnowledgeNamespace.name)
        result = await self.session.execute(stmt)
        namespaces = result.scalars().all()

        return [ns for ns in namespaces if ns.is_accessible(user_scopes)]

    async def add(
        self,
        question: str,
        answer: str,
        metadata: dict | None = None,
        namespace_slug: str | None = None,
    ) -> KnowledgeEntry:
        """
        Add a new knowledge entry with its embedding.

        Args:
            question: The question or topic
            answer: The answer or content
            metadata: Optional metadata dict
            namespace_slug: Optional namespace slug to categorize the entry

        Returns:
            The created KnowledgeEntry
        """
        embedding = await self.embedding_service.generate(question)

        # Resolve namespace ID from slug
        namespace_id = None
        if namespace_slug:
            namespace = await self.get_namespace_by_slug(namespace_slug)
            if namespace:
                namespace_id = namespace.id
            else:
                logger.warning(
                    "Namespace '%s' not found, entry will have no namespace", namespace_slug
                )

        entry = KnowledgeEntry(
            question=question,
            answer=answer,
            embedding=embedding,
            metadata_=metadata or {},
            namespace_id=namespace_id,
        )

        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)

        logger.info("Added knowledge entry: %s (namespace: %s)", entry.id, namespace_slug or "none")
        return entry

    async def add_batch(
        self,
        entries: list[dict],
        namespace_slug: str | None = None,
    ) -> list[KnowledgeEntry]:
        """
        Add multiple knowledge entries with their embeddings.

        Args:
            entries: List of dicts with 'question', 'answer', and optional 'metadata', 'namespace_slug'
            namespace_slug: Default namespace for all entries (can be overridden per entry)

        Returns:
            List of created KnowledgeEntry objects
        """
        if not entries:
            return []

        # Pre-fetch all unique namespace slugs
        namespace_slugs = set()
        if namespace_slug:
            namespace_slugs.add(namespace_slug)
        for entry in entries:
            if entry.get("namespace_slug"):
                namespace_slugs.add(entry["namespace_slug"])

        # Build slug -> id mapping
        namespace_map: dict[str, int] = {}
        for slug in namespace_slugs:
            ns = await self.get_namespace_by_slug(slug)
            if ns:
                namespace_map[slug] = ns.id

        questions = [e["question"] for e in entries]
        embeddings = await self.embedding_service.generate_batch(questions)

        knowledge_entries = []
        for entry, embedding in zip(entries, embeddings, strict=True):
            entry_ns_slug = entry.get("namespace_slug", namespace_slug)
            ns_id = namespace_map.get(entry_ns_slug) if entry_ns_slug else None

            knowledge_entry = KnowledgeEntry(
                question=entry["question"],
                answer=entry["answer"],
                embedding=embedding,
                metadata_=entry.get("metadata", {}),
                namespace_id=ns_id,
            )
            self.session.add(knowledge_entry)
            knowledge_entries.append(knowledge_entry)

        await self.session.commit()

        for ke in knowledge_entries:
            await self.session.refresh(ke)

        logger.info("Added %d knowledge entries in batch", len(knowledge_entries))
        return knowledge_entries

    async def get(self, entry_id: int) -> KnowledgeEntry | None:
        """Get a knowledge entry by ID."""
        stmt = select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, entry_id: int) -> bool:
        """Delete a knowledge entry by ID."""
        entry = await self.get(entry_id)
        if not entry:
            return False

        await self.session.delete(entry)
        await self.session.commit()
        logger.info("Deleted knowledge entry: %s", entry_id)
        return True

    async def update_embedding(self, entry_id: int) -> KnowledgeEntry | None:
        """Regenerate embedding for an existing entry."""
        entry = await self.get(entry_id)
        if not entry:
            return None

        entry.embedding = await self.embedding_service.generate(entry.question)
        await self.session.commit()
        await self.session.refresh(entry)

        logger.info("Updated embedding for entry: %s", entry_id)
        return entry
