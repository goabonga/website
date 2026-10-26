# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Knowledge base with pgvector for RAG-based responses.

This module provides semantic search over a PostgreSQL database with pgvector
to find relevant answers from a knowledge base.
"""

import logging
from dataclasses import dataclass

import asyncpg
from openai import AsyncOpenAI

from asterisk.config import config

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """A knowledge base entry with question and answer."""

    id: int
    question: str
    answer: str
    similarity: float


class KnowledgeBase:
    """Knowledge base with semantic search using pgvector."""

    def __init__(
        self,
        database_url: str,
        openai_api_key: str,
        embedding_model: str = "text-embedding-3-small",
        similarity_threshold: float = 0.7,
        max_results: int = 3,
    ):
        """Initialize the knowledge base.

        Args:
            database_url: PostgreSQL connection URL
            openai_api_key: OpenAI API key for embeddings
            embedding_model: OpenAI embedding model to use
            similarity_threshold: Minimum similarity score (0-1) to consider a match
            max_results: Maximum number of results to return
        """
        self.database_url = database_url
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.max_results = max_results
        self.pool: asyncpg.Pool | None = None
        self.openai = AsyncOpenAI(api_key=openai_api_key)

    async def connect(self):
        """Connect to the database."""
        try:
            self.pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5)
            logger.info("Connected to knowledge base database")

            # Ensure table and extension exist
            await self._ensure_schema()
        except Exception as e:
            logger.error(f"Failed to connect to knowledge base: {e}")
            raise

    async def disconnect(self):
        """Disconnect from the database."""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from knowledge base database")

    async def _ensure_schema(self):
        """Ensure the knowledge base table exists.

        In shared database mode, the table may already exist (created by another
        app like backend via Alembic). Skip DDL if the table is already present
        to avoid ownership permission errors.
        """
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            # Check if the table already exists
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'knowledge_base')"
            )

            if exists:
                logger.info("Knowledge base table already exists, skipping schema creation")
                return

            # Table doesn't exist — create everything
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_base (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS knowledge_base_embedding_idx
                ON knowledge_base USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """)

            logger.info("Knowledge base schema created")

    async def _get_embedding(self, text: str) -> list[float]:
        """Get embedding vector for text using OpenAI."""
        response = await self.openai.embeddings.create(model=self.embedding_model, input=text)
        return response.data[0].embedding

    async def search(self, query: str) -> list[KnowledgeEntry]:
        """Search the knowledge base for relevant entries.

        Args:
            query: The user's question

        Returns:
            List of matching entries sorted by similarity
        """
        if not self.pool:
            logger.warning("Knowledge base not connected")
            return []

        try:
            # Get embedding for the query
            embedding = await self._get_embedding(query)
            embedding_str = f"[{','.join(map(str, embedding))}]"

            async with self.pool.acquire() as conn:
                # Search using cosine similarity
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        question,
                        answer,
                        1 - (embedding <=> $1::vector) as similarity
                    FROM knowledge_base
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """,
                    embedding_str,
                    self.max_results,
                )

                results = []
                for row in rows:
                    if row["similarity"] >= self.similarity_threshold:
                        results.append(
                            KnowledgeEntry(
                                id=row["id"],
                                question=row["question"],
                                answer=row["answer"],
                                similarity=row["similarity"],
                            )
                        )

                logger.info(
                    f"Knowledge search for '{query[:50]}...' found {len(results)} matches "
                    f"(threshold: {self.similarity_threshold})"
                )
                return results

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []

    async def get_sample_questions(self, limit: int = 5) -> list[str]:
        """Get sample questions from the knowledge base.

        Args:
            limit: Maximum number of questions to return

        Returns:
            List of sample questions
        """
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT question
                    FROM knowledge_base
                    ORDER BY RANDOM()
                    LIMIT $1
                """,
                    limit,
                )
                return [row["question"] for row in rows]
        except Exception as e:
            logger.error(f"Error getting sample questions: {e}")
            return []

    async def add_entry(self, question: str, answer: str) -> int:
        """Add a new entry to the knowledge base.

        Args:
            question: The question
            answer: The answer

        Returns:
            The ID of the new entry
        """
        if not self.pool:
            raise RuntimeError("Knowledge base not connected")

        embedding = await self._get_embedding(question)
        embedding_str = f"[{','.join(map(str, embedding))}]"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_base (question, answer, embedding)
                VALUES ($1, $2, $3::vector)
                RETURNING id
            """,
                question,
                answer,
                embedding_str,
            )
            logger.info(f"Added knowledge entry {row['id']}: {question[:50]}...")
            return row["id"]

    async def update_entry(self, entry_id: int, question: str, answer: str):
        """Update an existing entry.

        Args:
            entry_id: The entry ID
            question: The new question
            answer: The new answer
        """
        if not self.pool:
            raise RuntimeError("Knowledge base not connected")

        embedding = await self._get_embedding(question)
        embedding_str = f"[{','.join(map(str, embedding))}]"

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_base
                SET question = $1, answer = $2, embedding = $3::vector,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $4
            """,
                question,
                answer,
                embedding_str,
                entry_id,
            )
            logger.info(f"Updated knowledge entry {entry_id}")

    async def delete_entry(self, entry_id: int):
        """Delete an entry from the knowledge base.

        Args:
            entry_id: The entry ID to delete
        """
        if not self.pool:
            raise RuntimeError("Knowledge base not connected")

        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM knowledge_base WHERE id = $1", entry_id)
            logger.info(f"Deleted knowledge entry {entry_id}")


# Global knowledge base instance
_knowledge_base: KnowledgeBase | None = None


async def get_knowledge_base() -> KnowledgeBase | None:
    """Get or create the global knowledge base instance."""
    global _knowledge_base

    if not config.RAG_ENABLED:
        return None

    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase(
            database_url=config.DATABASE_URL,
            openai_api_key=config.OPENAI_API_KEY,
            embedding_model=config.RAG_EMBEDDING_MODEL,
            similarity_threshold=config.RAG_SIMILARITY_THRESHOLD,
            max_results=config.RAG_MAX_RESULTS,
        )
        await _knowledge_base.connect()

    return _knowledge_base


async def close_knowledge_base():
    """Close the global knowledge base connection."""
    global _knowledge_base

    if _knowledge_base:
        await _knowledge_base.disconnect()
        _knowledge_base = None
