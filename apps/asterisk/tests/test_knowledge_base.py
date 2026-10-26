# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/knowledge_base.py."""

from unittest.mock import AsyncMock, patch

import pytest
from asterisk.knowledge_base import (
    KnowledgeBase,
    KnowledgeEntry,
    close_knowledge_base,
    get_knowledge_base,
)


@pytest.fixture
def kb(mock_openai_embeddings):
    """Return a KnowledgeBase with mocked OpenAI client."""
    with patch("asterisk.knowledge_base.AsyncOpenAI", return_value=mock_openai_embeddings):
        return KnowledgeBase(
            database_url="postgresql://test:test@localhost/test",
            openai_api_key="sk-test",
        )


@pytest.fixture
def kb_with_pool(kb, mock_asyncpg_pool):
    """Return a KnowledgeBase with a mocked pool."""
    pool, conn = mock_asyncpg_pool
    kb.pool = pool
    return kb, pool, conn


# --- KnowledgeEntry ---


class TestKnowledgeEntry:
    def test_dataclass_creation(self):
        entry = KnowledgeEntry(id=1, question="Q?", answer="A.", similarity=0.95)
        assert entry.id == 1
        assert entry.question == "Q?"
        assert entry.answer == "A."
        assert entry.similarity == 0.95


# --- KnowledgeBase Init ---


class TestKnowledgeBaseInit:
    def test_stores_parameters(self, kb):
        assert kb.database_url == "postgresql://test:test@localhost/test"
        assert kb.embedding_model == "text-embedding-3-small"
        assert kb.similarity_threshold == 0.7
        assert kb.max_results == 3

    def test_pool_is_none_initially(self, kb):
        assert kb.pool is None

    def test_custom_parameters(self, mock_openai_embeddings):
        with patch("asterisk.knowledge_base.AsyncOpenAI", return_value=mock_openai_embeddings):
            kb = KnowledgeBase(
                database_url="postgres://",
                openai_api_key="sk-test",
                embedding_model="text-embedding-3-large",
                similarity_threshold=0.5,
                max_results=10,
            )
        assert kb.embedding_model == "text-embedding-3-large"
        assert kb.similarity_threshold == 0.5
        assert kb.max_results == 10


# --- Connect / Disconnect ---


class TestConnect:
    @patch("asterisk.knowledge_base.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_creates_pool(self, mock_create_pool, kb, mock_asyncpg_pool):
        pool, conn = mock_asyncpg_pool
        mock_create_pool.return_value = pool
        await kb.connect()
        mock_create_pool.assert_called_once()
        assert kb.pool is pool

    @patch("asterisk.knowledge_base.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_calls_ensure_schema(self, mock_create_pool, kb, mock_asyncpg_pool):
        pool, conn = mock_asyncpg_pool
        mock_create_pool.return_value = pool
        await kb.connect()
        # _ensure_schema checks table existence, then runs DDL if not found
        conn.fetchval.assert_called_once()
        assert conn.execute.call_count >= 2

    @patch("asterisk.knowledge_base.asyncpg.create_pool", new_callable=AsyncMock)
    async def test_failure_raises(self, mock_create_pool, kb):
        mock_create_pool.side_effect = ConnectionRefusedError("refused")
        with pytest.raises(ConnectionRefusedError):
            await kb.connect()


class TestDisconnect:
    async def test_closes_pool(self, kb_with_pool):
        kb, pool, _ = kb_with_pool
        await kb.disconnect()
        pool.close.assert_called_once()

    async def test_no_pool_no_error(self, kb):
        kb.pool = None
        await kb.disconnect()


# --- Ensure Schema ---


class TestEnsureSchema:
    async def test_skips_ddl_when_table_exists(self, kb_with_pool):
        """When the table already exists (shared DB), skip all DDL."""
        kb, _, conn = kb_with_pool
        conn.fetchval = AsyncMock(return_value=True)
        await kb._ensure_schema()
        conn.fetchval.assert_called_once()
        conn.execute.assert_not_called()

    async def test_creates_vector_extension(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        await kb._ensure_schema()
        calls = [str(c) for c in conn.execute.call_args_list]
        assert any("CREATE EXTENSION" in c for c in calls)

    async def test_creates_table(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        await kb._ensure_schema()
        calls = [str(c) for c in conn.execute.call_args_list]
        assert any("CREATE TABLE" in c for c in calls)

    async def test_creates_index(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        await kb._ensure_schema()
        calls = [str(c) for c in conn.execute.call_args_list]
        assert any("CREATE INDEX" in c for c in calls)


# --- Get Embedding ---


class TestGetEmbedding:
    async def test_calls_openai_api(self, kb):
        result = await kb._get_embedding("test query")
        kb.openai.embeddings.create.assert_called_once()
        assert len(result) == 1536


# --- Search ---


class TestSearch:
    async def test_returns_matching_entries(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(
            return_value=[
                {"id": 1, "question": "Q1", "answer": "A1", "similarity": 0.9},
                {"id": 2, "question": "Q2", "answer": "A2", "similarity": 0.8},
            ]
        )

        results = await kb.search("test query")
        assert len(results) == 2
        assert isinstance(results[0], KnowledgeEntry)
        assert results[0].similarity == 0.9

    async def test_filters_below_threshold(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(
            return_value=[
                {"id": 1, "question": "Q1", "answer": "A1", "similarity": 0.5},
            ]
        )

        results = await kb.search("test query")
        assert len(results) == 0

    async def test_empty_results(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(return_value=[])

        results = await kb.search("test query")
        assert results == []

    async def test_no_pool_returns_empty(self, kb):
        kb.pool = None
        results = await kb.search("test query")
        assert results == []

    async def test_handles_exception(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(side_effect=RuntimeError("db error"))

        results = await kb.search("test query")
        assert results == []


# --- Get Sample Questions ---


class TestGetSampleQuestions:
    async def test_returns_questions(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(
            return_value=[
                {"question": "Q1"},
                {"question": "Q2"},
            ]
        )

        results = await kb.get_sample_questions(limit=5)
        assert results == ["Q1", "Q2"]

    async def test_no_pool_returns_empty(self, kb):
        kb.pool = None
        results = await kb.get_sample_questions()
        assert results == []

    async def test_handles_exception(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetch = AsyncMock(side_effect=RuntimeError("db error"))

        results = await kb.get_sample_questions()
        assert results == []


# --- Add Entry ---


class TestAddEntry:
    async def test_inserts_and_returns_id(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        conn.fetchrow = AsyncMock(return_value={"id": 42})

        result = await kb.add_entry("Q?", "A.")
        assert result == 42
        conn.fetchrow.assert_called_once()

    async def test_no_pool_raises(self, kb):
        kb.pool = None
        with pytest.raises(RuntimeError, match="not connected"):
            await kb.add_entry("Q?", "A.")


# --- Update Entry ---


class TestUpdateEntry:
    async def test_updates_row(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        await kb.update_entry(42, "New Q?", "New A.")
        conn.execute.assert_called_once()

    async def test_no_pool_raises(self, kb):
        kb.pool = None
        with pytest.raises(RuntimeError, match="not connected"):
            await kb.update_entry(1, "Q?", "A.")


# --- Delete Entry ---


class TestDeleteEntry:
    async def test_deletes_row(self, kb_with_pool):
        kb, _, conn = kb_with_pool
        await kb.delete_entry(42)
        conn.execute.assert_called_once()

    async def test_no_pool_raises(self, kb):
        kb.pool = None
        with pytest.raises(RuntimeError, match="not connected"):
            await kb.delete_entry(1)


# --- Singleton functions ---


class TestGetKnowledgeBaseSingleton:
    @patch("asterisk.knowledge_base.config")
    async def test_returns_none_when_rag_disabled(self, mock_config):
        mock_config.RAG_ENABLED = False
        result = await get_knowledge_base()
        assert result is None

    @patch("asterisk.knowledge_base.asyncpg.create_pool", new_callable=AsyncMock)
    @patch("asterisk.knowledge_base.AsyncOpenAI")
    @patch("asterisk.knowledge_base.config")
    async def test_creates_instance_when_rag_enabled(
        self, mock_config, MockOpenAI, mock_create_pool, mock_asyncpg_pool, mock_openai_embeddings
    ):
        mock_config.RAG_ENABLED = True
        mock_config.DATABASE_URL = "postgresql://test"
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config.RAG_EMBEDDING_MODEL = "text-embedding-3-small"
        mock_config.RAG_SIMILARITY_THRESHOLD = 0.7
        mock_config.RAG_MAX_RESULTS = 3
        MockOpenAI.return_value = mock_openai_embeddings

        pool, conn = mock_asyncpg_pool
        mock_create_pool.return_value = pool

        result = await get_knowledge_base()
        assert result is not None
        assert isinstance(result, KnowledgeBase)

    @patch("asterisk.knowledge_base.asyncpg.create_pool", new_callable=AsyncMock)
    @patch("asterisk.knowledge_base.AsyncOpenAI")
    @patch("asterisk.knowledge_base.config")
    async def test_returns_same_instance(
        self, mock_config, MockOpenAI, mock_create_pool, mock_asyncpg_pool, mock_openai_embeddings
    ):
        mock_config.RAG_ENABLED = True
        mock_config.DATABASE_URL = "postgresql://test"
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config.RAG_EMBEDDING_MODEL = "text-embedding-3-small"
        mock_config.RAG_SIMILARITY_THRESHOLD = 0.7
        mock_config.RAG_MAX_RESULTS = 3
        MockOpenAI.return_value = mock_openai_embeddings

        pool, conn = mock_asyncpg_pool
        mock_create_pool.return_value = pool

        first = await get_knowledge_base()
        second = await get_knowledge_base()
        assert first is second


class TestCloseKnowledgeBase:
    async def test_disconnects_and_clears(self):
        import asterisk.knowledge_base as kb_module

        mock_kb = AsyncMock()
        kb_module._knowledge_base = mock_kb

        await close_knowledge_base()
        mock_kb.disconnect.assert_called_once()
        assert kb_module._knowledge_base is None

    async def test_no_instance_no_error(self):
        import asterisk.knowledge_base as kb_module

        kb_module._knowledge_base = None
        await close_knowledge_base()
