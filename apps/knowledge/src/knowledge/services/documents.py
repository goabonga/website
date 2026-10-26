# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Document service for CRUD operations."""

import hashlib
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge.models.document import Document
from knowledge.schemas.document import DocumentCreate
from knowledge.services.collections import CollectionService
from knowledge.services.embeddings import get_embedding_service


class DocumentService:
    """Service for managing documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.embedding_service = get_embedding_service()
        self.collection_service = CollectionService(db)

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def _compute_content_size(content: str) -> int:
        """Compute UTF-8 byte size for content storage accounting."""
        return len(content.encode("utf-8"))

    @staticmethod
    def _compute_embedding_size(embedding: list[float]) -> int:
        """Estimate embedding size in bytes (float32 per dimension)."""
        return len(embedding) * 4

    async def create(
        self,
        collection_id: UUID,
        data: DocumentCreate,
    ) -> Document:
        """Create a new document with embedding.

        Args:
            collection_id: The collection ID.
            data: Document creation data.

        Returns:
            The created document.
        """
        # Generate embedding
        embedding = await self.embedding_service.embed_text(data.content)

        document = Document(
            collection_id=collection_id,
            content=data.content,
            embedding=embedding,
            doc_metadata=data.metadata,
            source_type=data.source_type,
            source_ref=data.source_ref,
            content_hash=self._compute_hash(data.content),
            content_size=self._compute_content_size(data.content),
            embedding_size=self._compute_embedding_size(embedding),
        )
        self.db.add(document)
        await self.db.flush()

        # Update collection document count
        await self.collection_service.increment_document_count(collection_id, 1)

        await self.db.refresh(document)
        return document

    async def create_batch(
        self,
        collection_id: UUID,
        documents: list[DocumentCreate],
    ) -> list[Document]:
        """Create multiple documents with embeddings.

        Args:
            collection_id: The collection ID.
            documents: List of document creation data.

        Returns:
            List of created documents.
        """
        if not documents:
            return []

        # Generate embeddings in batch
        contents = [doc.content for doc in documents]
        embeddings = await self.embedding_service.embed_texts(contents)

        created_docs = []
        for doc_data, embedding in zip(documents, embeddings, strict=True):
            document = Document(
                collection_id=collection_id,
                content=doc_data.content,
                embedding=embedding,
                doc_metadata=doc_data.metadata,
                source_type=doc_data.source_type,
                source_ref=doc_data.source_ref,
                content_hash=self._compute_hash(doc_data.content),
                content_size=self._compute_content_size(doc_data.content),
                embedding_size=self._compute_embedding_size(embedding),
            )
            self.db.add(document)
            created_docs.append(document)

        await self.db.flush()

        # Update collection document count
        await self.collection_service.increment_document_count(collection_id, len(documents))

        for doc in created_docs:
            await self.db.refresh(doc)

        return created_docs

    async def get_by_id(
        self,
        document_id: UUID,
        collection_id: UUID | None = None,
    ) -> Document | None:
        """Get a document by ID.

        Args:
            document_id: The document ID.
            collection_id: Optional collection ID for filtering.

        Returns:
            The document or None if not found.
        """
        query = select(Document).where(Document.id == document_id)
        if collection_id:
            query = query.where(Document.collection_id == collection_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        collection_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """List documents in a collection.

        Args:
            collection_id: The collection ID.
            offset: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of documents.
        """
        result = await self.db.execute(
            select(Document)
            .where(Document.collection_id == collection_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, document_id: UUID, collection_id: UUID) -> bool:
        """Delete a document.

        Args:
            document_id: The document ID.
            collection_id: The collection ID.

        Returns:
            True if deleted, False if not found.
        """
        document = await self.get_by_id(document_id, collection_id)
        if not document:
            return False

        await self.db.delete(document)
        await self.db.flush()

        # Update collection document count
        await self.collection_service.increment_document_count(collection_id, -1)

        return True

    async def delete_by_collection(self, collection_id: UUID) -> int:
        """Delete all documents in a collection.

        Args:
            collection_id: The collection ID.

        Returns:
            Number of documents deleted.
        """
        result = await self.db.execute(
            delete(Document).where(Document.collection_id == collection_id)
        )
        await self.db.flush()
        return result.rowcount or 0  # type: ignore[attr-defined]

    async def exists_by_hash(self, collection_id: UUID, content_hash: str) -> bool:
        """Check if a document with the given hash exists.

        Args:
            collection_id: The collection ID.
            content_hash: The content hash to check.

        Returns:
            True if exists, False otherwise.
        """
        result = await self.db.execute(
            select(Document.id).where(
                Document.collection_id == collection_id,
                Document.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none() is not None
