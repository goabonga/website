# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.rag.knowledge_base.KnowledgeBase."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session():
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_embedding_service():
    """Return a mocked EmbeddingService."""
    svc = AsyncMock()
    svc.generate = AsyncMock(return_value=[0.1, 0.2, 0.3])
    svc.generate_batch = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
    return svc


@pytest.fixture
def knowledge_base(mock_session, mock_embedding_service):
    """Create a KnowledgeBase with mocked dependencies."""
    with (
        patch("backend.rag.knowledge_base.EmbeddingService", return_value=mock_embedding_service),
        patch("backend.rag.knowledge_base.settings") as mock_settings,
    ):
        mock_settings.rag_max_results = 5
        mock_settings.rag_similarity_threshold = 0.7
        from backend.rag.knowledge_base import KnowledgeBase

        kb = KnowledgeBase(session=mock_session)
        # Ensure the patched embedding service is used
        kb.embedding_service = mock_embedding_service
        yield kb


def _make_namespace(ns_id, slug, name, is_public=True, required_scopes=None):
    """Helper to create a mock KnowledgeNamespace."""
    ns = MagicMock()
    ns.id = ns_id
    ns.slug = slug
    ns.name = name
    ns.is_public = is_public
    ns.required_scopes = required_scopes

    # Replicate the real is_accessible logic
    def is_accessible(user_scopes):
        if is_public and not required_scopes:
            return True
        if not is_public and user_scopes is None:
            return False
        if required_scopes:
            if user_scopes is None:
                return False
            return set(required_scopes).issubset(user_scopes)
        return is_public

    ns.is_accessible = is_accessible
    return ns


def _make_entry(entry_id, question, answer, namespace_id=None):
    """Helper to create a mock KnowledgeEntry."""
    entry = MagicMock()
    entry.id = entry_id
    entry.question = question
    entry.answer = answer
    entry.namespace_id = namespace_id
    entry.metadata_ = {}
    entry.embedding = [0.1, 0.2, 0.3]
    return entry


class TestGetAccessibleNamespaceIds:
    """Tests for _get_accessible_namespace_ids."""

    async def test_with_public_namespaces(self, knowledge_base, mock_session):
        """Public namespaces with no required scopes should be accessible to anyone."""
        ns1 = _make_namespace(1, "public", "Public", is_public=True)
        ns2 = _make_namespace(2, "also-public", "Also Public", is_public=True)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ns1, ns2]
        mock_session.execute.return_value = mock_result

        result = await knowledge_base._get_accessible_namespace_ids(user_scopes=None)

        assert result == [1, 2]

    async def test_with_scoped_namespaces(self, knowledge_base, mock_session):
        """Scoped namespaces should only be accessible to users with matching scopes."""
        ns_public = _make_namespace(1, "public", "Public", is_public=True)
        ns_scoped = _make_namespace(
            2, "admin", "Admin", is_public=False, required_scopes=["admin:read"]
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ns_public, ns_scoped]
        mock_session.execute.return_value = mock_result

        # User without admin scope
        result = await knowledge_base._get_accessible_namespace_ids(user_scopes={"openid"})
        assert result == [1]

        # User with admin scope
        mock_session.execute.return_value = mock_result
        result = await knowledge_base._get_accessible_namespace_ids(
            user_scopes={"openid", "admin:read"}
        )
        assert result == [1, 2]


class TestSearch:
    """Tests for search."""

    async def test_search_returns_results(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """search() should return formatted results when matches are found."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        # Mock _get_accessible_namespace_ids
        with patch.object(
            knowledge_base, "_get_accessible_namespace_ids", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = [1]

            mock_row = MagicMock()
            mock_row.id = 1
            mock_row.question = "What is Python?"
            mock_row.answer = "A programming language."
            mock_row.metadata = {}
            mock_row.namespace_id = 1
            mock_row.namespace_slug = "general"
            mock_row.namespace_name = "General"
            mock_row.similarity = 0.95

            mock_result = MagicMock()
            mock_result.fetchall.return_value = [mock_row]
            mock_session.execute.return_value = mock_result

            results = await knowledge_base.search("What is Python?")

            assert len(results) == 1
            assert results[0]["id"] == 1
            assert results[0]["question"] == "What is Python?"
            assert results[0]["similarity"] == 0.95
            assert results[0]["namespace"]["slug"] == "general"

    async def test_search_returns_empty_list(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """search() should return an empty list when no matches are found."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        with patch.object(
            knowledge_base, "_get_accessible_namespace_ids", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = [1]

            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_session.execute.return_value = mock_result

            results = await knowledge_base.search("Unknown topic")

            assert results == []


class TestGetNamespaceBySlug:
    """Tests for get_namespace_by_slug."""

    async def test_found(self, knowledge_base, mock_session):
        """get_namespace_by_slug() should return the namespace when found."""
        ns = _make_namespace(1, "general", "General")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ns
        mock_session.execute.return_value = mock_result

        result = await knowledge_base.get_namespace_by_slug("general")

        assert result == ns
        assert result.slug == "general"

    async def test_not_found(self, knowledge_base, mock_session):
        """get_namespace_by_slug() should return None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await knowledge_base.get_namespace_by_slug("nonexistent")

        assert result is None


class TestListNamespaces:
    """Tests for list_namespaces."""

    async def test_filters_by_accessibility(self, knowledge_base, mock_session):
        """list_namespaces() should only return namespaces accessible to the user."""
        ns_public = _make_namespace(1, "public", "Public", is_public=True)
        ns_private = _make_namespace(
            2, "private", "Private", is_public=False, required_scopes=["admin"]
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ns_public, ns_private]
        mock_session.execute.return_value = mock_result

        # Anonymous user should only see public
        result = await knowledge_base.list_namespaces(user_scopes=None)

        assert len(result) == 1
        assert result[0].slug == "public"


class TestAdd:
    """Tests for add."""

    async def test_creates_entry_with_embedding(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add() should create a KnowledgeEntry with a generated embedding."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        await knowledge_base.add(
            question="What is Python?",
            answer="A programming language.",
        )

        mock_embedding_service.generate.assert_awaited_once_with("What is Python?")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()


class TestAddBatch:
    """Tests for add_batch."""

    async def test_with_multiple_entries(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add_batch() should create multiple entries with embeddings."""
        mock_embedding_service.generate_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

        entries_data = [
            {"question": "Q1", "answer": "A1"},
            {"question": "Q2", "answer": "A2"},
        ]

        await knowledge_base.add_batch(entries_data)

        mock_embedding_service.generate_batch.assert_awaited_once_with(["Q1", "Q2"])
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_awaited_once()

    async def test_with_empty_list_returns_empty(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add_batch() with an empty list should return an empty list."""
        result = await knowledge_base.add_batch([])

        assert result == []
        mock_embedding_service.generate_batch.assert_not_awaited()
        mock_session.commit.assert_not_awaited()


class TestGet:
    """Tests for get."""

    async def test_returns_entry(self, knowledge_base, mock_session):
        """get() should return the entry when found."""
        entry = _make_entry(1, "Q1", "A1")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entry
        mock_session.execute.return_value = mock_result

        result = await knowledge_base.get(1)

        assert result == entry
        assert result.id == 1


class TestDelete:
    """Tests for delete."""

    async def test_existing_returns_true(self, knowledge_base, mock_session):
        """delete() should return True when the entry exists and is deleted."""
        entry = _make_entry(1, "Q1", "A1")

        with patch.object(knowledge_base, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = entry

            result = await knowledge_base.delete(1)

            assert result is True
            mock_session.delete.assert_awaited_once_with(entry)
            mock_session.commit.assert_awaited_once()

    async def test_non_existing_returns_false(self, knowledge_base, mock_session):
        """delete() should return False when the entry does not exist."""
        with patch.object(knowledge_base, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await knowledge_base.delete(999)

            assert result is False
            mock_session.delete.assert_not_awaited()


class TestSearchAdditional:
    """Additional tests for search covering namespace and empty access branches."""

    async def test_search_with_namespace_slug(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """search(namespace_slug=...) should filter by specific namespace slug."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.question = "What is Python?"
        mock_row.answer = "A language."
        mock_row.metadata = {}
        mock_row.namespace_id = 1
        mock_row.namespace_slug = "specific-ns"
        mock_row.namespace_name = "Specific NS"
        mock_row.similarity = 0.9

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        results = await knowledge_base.search("What is Python?", namespace_slug="specific-ns")

        assert len(results) == 1
        assert results[0]["namespace"]["slug"] == "specific-ns"
        mock_embedding_service.generate.assert_awaited_once_with("What is Python?")

    async def test_search_no_accessible_namespaces(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """search() with no accessible namespaces should add 'namespace_id IS NULL' clause."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        with patch.object(
            knowledge_base, "_get_accessible_namespace_ids", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = []  # No accessible namespaces

            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_session.execute.return_value = mock_result

            results = await knowledge_base.search("query", user_scopes=None)

        assert results == []
        mock_get_ns.assert_awaited_once()


class TestCreateNamespace:
    """Tests for create_namespace."""

    async def test_create_namespace(self, knowledge_base, mock_session):
        """create_namespace() should create and return a new namespace."""
        await knowledge_base.create_namespace(
            slug="new-ns",
            name="New Namespace",
            description="A test namespace",
            required_scopes=["admin"],
            is_public=False,
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

        added = mock_session.add.call_args[0][0]
        assert added.slug == "new-ns"
        assert added.name == "New Namespace"
        assert added.is_public is False


class TestAddAdditional:
    """Additional tests for add covering namespace branches."""

    async def test_add_with_namespace(self, knowledge_base, mock_session, mock_embedding_service):
        """add(namespace_slug=...) should resolve namespace_id from slug."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        ns = _make_namespace(5, "my-ns", "My Namespace")
        with patch.object(
            knowledge_base, "get_namespace_by_slug", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = ns

            await knowledge_base.add(
                question="Q",
                answer="A",
                namespace_slug="my-ns",
            )

        mock_get_ns.assert_awaited_once_with("my-ns")
        added = mock_session.add.call_args[0][0]
        assert added.namespace_id == 5

    async def test_add_with_nonexistent_namespace(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add() with a non-existent namespace slug should log warning and create without namespace."""
        mock_embedding_service.generate.return_value = [0.1, 0.2, 0.3]

        with patch.object(
            knowledge_base, "get_namespace_by_slug", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = None

            await knowledge_base.add(
                question="Q",
                answer="A",
                namespace_slug="nonexistent",
            )

        mock_get_ns.assert_awaited_once_with("nonexistent")
        added = mock_session.add.call_args[0][0]
        assert added.namespace_id is None


class TestAddBatchAdditional:
    """Additional tests for add_batch covering namespace mapping."""

    async def test_add_batch_with_namespaces(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add_batch() with different namespace slugs should resolve and map them."""
        mock_embedding_service.generate_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

        ns1 = _make_namespace(10, "ns-a", "NS A")
        ns2 = _make_namespace(20, "ns-b", "NS B")

        ns_map = {"ns-a": ns1, "ns-b": ns2}

        with patch.object(
            knowledge_base, "get_namespace_by_slug", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.side_effect = lambda slug: ns_map.get(slug)

            entries_data = [
                {"question": "Q1", "answer": "A1", "namespace_slug": "ns-a"},
                {"question": "Q2", "answer": "A2", "namespace_slug": "ns-b"},
            ]

            await knowledge_base.add_batch(entries_data)

        assert mock_session.add.call_count == 2
        mock_session.commit.assert_awaited_once()

        # Verify namespace_id was resolved for each entry
        first_add = mock_session.add.call_args_list[0][0][0]
        second_add = mock_session.add.call_args_list[1][0][0]
        assert first_add.namespace_id == 10
        assert second_add.namespace_id == 20


class TestAddBatchWithDefaultNamespace:
    """Tests for add_batch with a default namespace_slug parameter."""

    async def test_add_batch_with_default_namespace_and_mixed_entries(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add_batch() with a default namespace_slug resolves default and per-entry namespaces."""
        mock_embedding_service.generate_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

        ns_default = _make_namespace(30, "default-ns", "Default NS")

        with patch.object(
            knowledge_base, "get_namespace_by_slug", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.side_effect = lambda slug: ns_default if slug == "default-ns" else None

            entries_data = [
                {"question": "Q1", "answer": "A1"},  # No per-entry namespace_slug
                {"question": "Q2", "answer": "A2"},
            ]

            await knowledge_base.add_batch(entries_data, namespace_slug="default-ns")

        # Should have resolved the default namespace
        mock_get_ns.assert_awaited_once_with("default-ns")
        assert mock_session.add.call_count == 2

        # Both entries should use the default namespace
        first_add = mock_session.add.call_args_list[0][0][0]
        second_add = mock_session.add.call_args_list[1][0][0]
        assert first_add.namespace_id == 30
        assert second_add.namespace_id == 30


class TestUpdateEmbedding:
    """Tests for update_embedding."""

    async def test_update_embedding(self, knowledge_base, mock_session, mock_embedding_service):
        """update_embedding() should regenerate the embedding for an existing entry."""
        entry = _make_entry(1, "What is Python?", "A language.")
        mock_embedding_service.generate.return_value = [0.9, 0.8, 0.7]

        with patch.object(knowledge_base, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = entry

            result = await knowledge_base.update_embedding(1)

        assert result is entry
        mock_embedding_service.generate.assert_awaited_once_with("What is Python?")
        assert entry.embedding == [0.9, 0.8, 0.7]
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    async def test_update_embedding_not_found(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """update_embedding() should return None when the entry does not exist."""
        with patch.object(knowledge_base, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await knowledge_base.update_embedding(999)

        assert result is None
        mock_embedding_service.generate.assert_not_awaited()


class TestAddBatchNamespaceNotFound:
    """Tests for add_batch when namespace slug is not found."""

    async def test_add_batch_namespace_slug_not_found(
        self, knowledge_base, mock_session, mock_embedding_service
    ):
        """add_batch skips namespace_id when get_namespace_by_slug returns None."""
        entries = [
            {"question": "Q1", "answer": "A1", "namespace_slug": "nonexistent"},
        ]
        mock_embedding_service.generate_batch.return_value = [[0.1, 0.2]]

        with patch.object(
            knowledge_base, "get_namespace_by_slug", new_callable=AsyncMock
        ) as mock_get_ns:
            mock_get_ns.return_value = None  # Namespace not found

            await knowledge_base.add_batch(entries, namespace_slug=None)

        # The entry was still created, but without a namespace_id
        assert mock_session.add.called
        mock_session.commit.assert_awaited_once()
        mock_get_ns.assert_awaited_once_with("nonexistent")
