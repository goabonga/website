# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for app/routes/knowledge.py - Knowledge Base CRUD routes."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse
from internal.auth.models import User

USER_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_user(**kwargs):
    defaults = {
        "id": USER_UUID,
        "email": "test@example.com",
        "name": "Test",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    req.cookies = kwargs.get("cookies", {})
    return req


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()  # add() is synchronous in SQLAlchemy
    return db


def _make_namespace(**kwargs):
    ns = MagicMock()
    ns.id = kwargs.get("id", 1)
    ns.slug = kwargs.get("slug", "general")
    ns.name = kwargs.get("name", "General")
    return ns


def _make_entry(**kwargs):
    entry = MagicMock()
    entry.id = kwargs.get("id", 1)
    entry.question = kwargs.get("question", "What is X?")
    entry.answer = kwargs.get("answer", "X is Y.")
    entry.embedding = kwargs.get("embedding")
    entry.metadata_ = kwargs.get("metadata_", {})
    entry.namespace_id = kwargs.get("namespace_id", 1)
    return entry


# =========================================================================
# Helper functions
# =========================================================================


class TestGetEmbeddingService:
    def test_returns_none_when_no_api_key(self):
        from internal.routes.knowledge import get_embedding_service

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = get_embedding_service()
            assert result is None

    def test_returns_service_when_configured(self):
        from internal.routes.knowledge import get_embedding_service

        with (
            patch("internal.routes.knowledge.settings") as mock_settings,
            patch("internal.routes.knowledge.EmbeddingService") as MockService,
        ):
            mock_settings.openai_api_key = "sk-test"
            MockService.return_value = MagicMock()
            result = get_embedding_service()
            assert result is not None


class TestGetGeneratorService:
    """get_generator_service was removed; generation now happens in Celery task."""

    pass


class TestGetOrCreateDefaultNamespace:
    @pytest.mark.asyncio
    async def test_exists(self):
        from internal.routes.knowledge import get_or_create_default_namespace

        db = _make_db()
        ns = _make_namespace()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_or_create_default_namespace(db)
        assert result is ns

    @pytest.mark.asyncio
    async def test_creates_new(self):
        from internal.routes.knowledge import get_or_create_default_namespace

        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        await get_or_create_default_namespace(db)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()


class TestGetAllNamespaces:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        from internal.routes.knowledge import get_all_namespaces

        db = _make_db()
        ns1 = _make_namespace(id=1)
        ns2 = _make_namespace(id=2)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [ns1, ns2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await get_all_namespaces(db)
        assert len(result) == 2


# =========================================================================
# Knowledge List
# =========================================================================


class TestKnowledgeList:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_list(
            request=req, page=1, search=None, namespace=None, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_list_no_filters(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={"success": "Created", "error": None})
        db = _make_db()
        user = _make_user()

        # get_all_namespaces
        ns = _make_namespace()
        ns_scalars = MagicMock()
        ns_scalars.all.return_value = [ns]
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        db.scalar = AsyncMock(return_value=5)

        entry = _make_entry()
        entry_scalars = MagicMock()
        entry_scalars.all.return_value = [entry]
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars

        db.execute = AsyncMock(side_effect=[ns_result, entry_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req, page=1, search=None, namespace=None, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 5
            assert call_kwargs["context"]["openai_configured"] is True
            assert call_kwargs["context"]["success"] == "Created"

    @pytest.mark.asyncio
    async def test_list_with_namespace_filter(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        # get_all_namespaces
        ns = _make_namespace(slug="custom")
        ns_scalars = MagicMock()
        ns_scalars.all.return_value = [ns]
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        # namespace filter lookup
        filter_ns = _make_namespace(id=2, slug="custom")
        filter_result = MagicMock()
        filter_result.scalar_one_or_none.return_value = filter_ns

        db.scalar = AsyncMock(return_value=1)

        entry_scalars = MagicMock()
        entry_scalars.all.return_value = []
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars

        db.execute = AsyncMock(side_effect=[ns_result, filter_result, entry_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req,
                page=1,
                search=None,
                namespace="custom",
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["namespace_filter"] == "custom"
            assert call_kwargs["context"]["openai_configured"] is False

    @pytest.mark.asyncio
    async def test_list_with_namespace_not_found(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ns_scalars = MagicMock()
        ns_scalars.all.return_value = []
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        filter_result = MagicMock()
        filter_result.scalar_one_or_none.return_value = None

        db.scalar = AsyncMock(return_value=0)
        entry_scalars = MagicMock()
        entry_scalars.all.return_value = []
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars

        db.execute = AsyncMock(side_effect=[ns_result, filter_result, entry_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req,
                page=1,
                search=None,
                namespace="nonexistent",
                db=db,
                auth_result=user,
            )
            # Should still render, just without namespace filter applied
            mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_with_search(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ns_scalars = MagicMock()
        ns_scalars.all.return_value = []
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        db.scalar = AsyncMock(return_value=0)
        entry_scalars = MagicMock()
        entry_scalars.all.return_value = []
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars

        db.execute = AsyncMock(side_effect=[ns_result, entry_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req,
                page=1,
                search="test query",
                namespace=None,
                db=db,
                auth_result=user,
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["search"] == "test query"

    @pytest.mark.asyncio
    async def test_list_zero_total(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ns_scalars = MagicMock()
        ns_scalars.all.return_value = []
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        db.scalar = AsyncMock(return_value=None)
        entry_scalars = MagicMock()
        entry_scalars.all.return_value = []
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars

        db.execute = AsyncMock(side_effect=[ns_result, entry_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req, page=1, search=None, namespace=None, db=db, auth_result=user
            )

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 0
            assert call_kwargs["context"]["total_pages"] == 1


# =========================================================================
# Knowledge New
# =========================================================================


class TestKnowledgeNew:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_new

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_new(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_form_displayed(self):
        from internal.routes.knowledge import knowledge_new

        req = _make_request()
        db = _make_db()
        user = _make_user()

        # get_or_create_default_namespace
        default_ns = _make_namespace(id=1, slug="general")
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = default_ns

        # get_all_namespaces
        ns_scalars = MagicMock()
        ns_scalars.all.return_value = [default_ns]
        all_ns_result = MagicMock()
        all_ns_result.scalars.return_value = ns_scalars

        db.execute = AsyncMock(side_effect=[ns_result, all_ns_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_new(request=req, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["entry"] is None
            assert call_kwargs["context"]["is_edit"] is False


# =========================================================================
# Knowledge Generate Form
# =========================================================================


class TestKnowledgeGenerateForm:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_generate_form

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_generate_form(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_openai_not_configured(self):
        from internal.routes.knowledge import knowledge_generate_form

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_generate_form(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "OpenAI+not+configured" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_form_displayed(self):
        from internal.routes.knowledge import knowledge_generate_form

        req = _make_request()
        db = _make_db()
        user = _make_user()

        default_ns = _make_namespace(id=1)
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = default_ns

        ns_scalars = MagicMock()
        ns_scalars.all.return_value = [default_ns]
        all_ns_result = MagicMock()
        all_ns_result.scalars.return_value = ns_scalars

        db.execute = AsyncMock(side_effect=[ns_result, all_ns_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "sk-test"
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_generate_form(request=req, db=db, auth_result=user)

            mock_templates.TemplateResponse.assert_called_once()


# =========================================================================
# Knowledge Generate (POST)
# =========================================================================


class TestKnowledgeGenerate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_generate(
            request=req,
            source_text="test",
            namespace_id=1,
            num_entries=5,
            context="",
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_openai_not_configured(self):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = await knowledge_generate(
                request=req,
                source_text="Some long source text for testing",
                namespace_id=1,
                num_entries=5,
                context="",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 400
        assert b"OpenAI not configured" in result.body

    @pytest.mark.asyncio
    async def test_source_text_too_short(self):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            result = await knowledge_generate(
                request=req,
                source_text="Short",
                namespace_id=1,
                num_entries=5,
                context="",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 400
        assert b"too short" in result.body

    @pytest.mark.asyncio
    async def test_dispatch_success(self, mock_celery_generation_task):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(slug="general")
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=ns_result)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_generate(
                request=req,
                source_text="A" * 60,
                namespace_id=1,
                num_entries=5,
                context="some context",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 200
        assert b"task_id" in result.body
        mock_celery_generation_task.assert_called_once_with("A" * 60, 5, "some context", 1)

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_context(self, mock_celery_generation_task):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(slug="general")
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=ns_result)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_generate(
                request=req,
                source_text="A" * 60,
                namespace_id=1,
                num_entries=5,
                context="   ",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 200
        # Empty context should be passed as None
        mock_celery_generation_task.assert_called_once_with("A" * 60, 5, None, 1)

    @pytest.mark.asyncio
    async def test_namespace_not_found_fallback_default(self, mock_celery_generation_task):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        # namespace lookup returns None
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = None

        # get_or_create_default_namespace
        default_ns = _make_namespace(id=99, slug="general")
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = default_ns

        db.execute = AsyncMock(side_effect=[ns_result, default_result])

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            result = await knowledge_generate(
                request=req,
                source_text="A" * 60,
                namespace_id=999,
                num_entries=5,
                context="",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 200
        # Should have used the default namespace_id
        call_args = mock_celery_generation_task.call_args[0]
        assert call_args[3] == 99  # namespace_id

    @pytest.mark.asyncio
    async def test_dispatch_failure(self, mock_celery_generation_task):
        from internal.routes.knowledge import knowledge_generate

        mock_celery_generation_task.side_effect = Exception("Redis down")

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=ns_result)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            result = await knowledge_generate(
                request=req,
                source_text="A" * 60,
                namespace_id=1,
                num_entries=5,
                context="",
                db=db,
                auth_result=user,
            )

        assert result.status_code == 500
        assert b"Failed to start generation task" in result.body

    @pytest.mark.asyncio
    async def test_clamps_num_entries(self, mock_celery_generation_task):
        from internal.routes.knowledge import knowledge_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=ns_result)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.oauth2_client_id = "test-client"
            await knowledge_generate(
                request=req,
                source_text="A" * 60,
                namespace_id=1,
                num_entries=100,
                context="",
                db=db,
                auth_result=user,
            )

        # num_entries=100 should be clamped to 50
        call_args = mock_celery_generation_task.call_args[0]
        assert call_args[1] == 50


# =========================================================================
# Knowledge Create
# =========================================================================


class TestKnowledgeCreate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_create(
            request=req,
            question="Q?",
            answer="A.",
            namespace_id=1,
            metadata_json="{}",
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result = await knowledge_create(
            request=req,
            question="Q?",
            answer="A.",
            namespace_id=1,
            metadata_json="invalid json{",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Invalid+JSON" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_namespace_not_found_fallback(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = None

        default_ns = _make_namespace(id=1, slug="general")
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = default_ns

        db.execute = AsyncMock(side_effect=[ns_result, default_result])

        with (
            patch("internal.routes.knowledge.get_embedding_service", return_value=None),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=999,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_create_with_embedding(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(return_value=[0.1, 0.2])

        with (
            patch(
                "internal.routes.knowledge.get_embedding_service",
                return_value=mock_embedding,
            ),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json='{"key": "val"}',
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_embedding_failure(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(side_effect=Exception("API error"))

        with patch(
            "internal.routes.knowledge.get_embedding_service",
            return_value=mock_embedding,
        ):
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+generate+embedding" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_create_no_embedding_service(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        with (
            patch("internal.routes.knowledge.get_embedding_service", return_value=None),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json="",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


# =========================================================================
# Knowledge Detail
# =========================================================================


class TestKnowledgeDetail:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_detail

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_detail(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.knowledge import knowledge_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_detail(request=req, entry_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_found(self):
        from internal.routes.knowledge import knowledge_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_detail(request=req, entry_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["entry"] is entry


# =========================================================================
# Knowledge Edit
# =========================================================================


class TestKnowledgeEdit:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_edit

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_edit(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.knowledge import knowledge_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_edit(request=req, entry_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_found(self):
        from internal.routes.knowledge import knowledge_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        # get_all_namespaces
        ns = _make_namespace()
        ns_scalars = MagicMock()
        ns_scalars.all.return_value = [ns]
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        # get_or_create_default_namespace
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = ns

        db.execute = AsyncMock(side_effect=[entry_result, ns_result, default_result])

        with (
            patch("internal.routes.knowledge.templates") as mock_templates,
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_edit(request=req, entry_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["entry"] is entry
            assert call_kwargs["context"]["is_edit"] is True


# =========================================================================
# Knowledge Update
# =========================================================================


class TestKnowledgeUpdate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_update(
            request=req,
            entry_id=1,
            question="Q?",
            answer="A.",
            namespace_id=1,
            metadata_json="{}",
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_update(
            request=req,
            entry_id=999,
            question="Q?",
            answer="A.",
            namespace_id=1,
            metadata_json="{}",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_update(
            request=req,
            entry_id=1,
            question="Q?",
            answer="A.",
            namespace_id=1,
            metadata_json="invalid{",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Invalid+JSON" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_question_changed_with_embedding(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Old question")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()

        db.execute = AsyncMock(side_effect=[entry_result, ns_result])

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(return_value=[0.1, 0.2])

        with (
            patch(
                "internal.routes.knowledge.get_embedding_service",
                return_value=mock_embedding,
            ),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="New question",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_question_changed_embedding_fails(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Old question")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()

        db.execute = AsyncMock(side_effect=[entry_result, ns_result])

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(side_effect=Exception("fail"))

        with patch(
            "internal.routes.knowledge.get_embedding_service",
            return_value=mock_embedding,
        ):
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="New question",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+generate+embedding" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_question_changed_no_embedding_service(self):
        """Covers branch 565->583: question changed but embedding service is None."""
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Old question")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()

        db.execute = AsyncMock(side_effect=[entry_result, ns_result])

        with (
            patch(
                "internal.routes.knowledge.get_embedding_service",
                return_value=None,  # No embedding service
            ),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="New question",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_question_not_changed(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Same question")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()

        db.execute = AsyncMock(side_effect=[entry_result, ns_result])

        with (
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="Same question",
                answer="Updated answer",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_namespace_not_found_fallback(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Same question")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        # namespace lookup fails
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = None

        # get_or_create_default_namespace
        default_ns = _make_namespace(id=99)
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = default_ns

        db.execute = AsyncMock(side_effect=[entry_result, ns_result, default_result])

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="Same question",
                answer="A.",
                namespace_id=999,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_empty_metadata_json(self):
        from internal.routes.knowledge import knowledge_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry(question="Q")
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(side_effect=[entry_result, ns_result])

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_update(
                request=req,
                entry_id=1,
                question="Q",
                answer="A.",
                namespace_id=1,
                metadata_json="",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


# =========================================================================
# Knowledge Regenerate Embedding
# =========================================================================


class TestKnowledgeRegenerateEmbedding:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_regenerate_embedding

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_regenerate_embedding(
            request=req, entry_id=1, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_no_embedding_service(self):
        from internal.routes.knowledge import knowledge_regenerate_embedding

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.knowledge.get_embedding_service", return_value=None):
            result = await knowledge_regenerate_embedding(
                request=req, entry_id=1, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert "OpenAI+not+configured" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        from internal.routes.knowledge import knowledge_regenerate_embedding

        req = _make_request()
        db = _make_db()
        user = _make_user()

        mock_embedding = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.get_embedding_service", return_value=mock_embedding):
            result = await knowledge_regenerate_embedding(
                request=req, entry_id=999, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_regenerate_success(self):
        from internal.routes.knowledge import knowledge_regenerate_embedding

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(return_value=[0.1, 0.2])

        with (
            patch(
                "internal.routes.knowledge.get_embedding_service",
                return_value=mock_embedding,
            ),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_regenerate_embedding(
                request=req, entry_id=1, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_regenerate_failure(self):
        from internal.routes.knowledge import knowledge_regenerate_embedding

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        mock_embedding = AsyncMock()
        mock_embedding.generate = AsyncMock(side_effect=Exception("API error"))

        with patch(
            "internal.routes.knowledge.get_embedding_service",
            return_value=mock_embedding,
        ):
            result = await knowledge_regenerate_embedding(
                request=req, entry_id=1, db=db, auth_result=user
            )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+regenerate" in result.headers.get("location", "")


# =========================================================================
# Knowledge Delete
# =========================================================================


class TestKnowledgeDelete:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_delete(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.knowledge import knowledge_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_delete(request=req, entry_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from internal.routes.knowledge import knowledge_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_delete(request=req, entry_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(entry)
        db.commit.assert_awaited_once()


# =========================================================================
# Knowledge Bulk Delete
# =========================================================================


class TestKnowledgeBulkDelete:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_bulk_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_bulk_delete(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_no_ids_selected(self):
        from internal.routes.knowledge import knowledge_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.get.return_value = ""
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await knowledge_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+entries+selected" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_invalid_ids(self):
        from internal.routes.knowledge import knowledge_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.get.return_value = "abc,def"
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await knowledge_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_no_entries_found(self):
        from internal.routes.knowledge import knowledge_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.get.return_value = "1,2"
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+entries+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_bulk_delete_success(self):
        from internal.routes.knowledge import knowledge_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.get.return_value = "1,2"
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        e1 = _make_entry(id=1)
        e2 = _make_entry(id=2)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [e1, e2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_bulk_delete(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "2+entry(ies)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2


# =========================================================================
# Validation Routes
# =========================================================================


class TestKnowledgeValidationDetail:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_validation_detail

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_validation_detail(
            request=req, entry_id=1, db=db, auth_result=redirect
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        from internal.routes.knowledge import knowledge_validation_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_validation_detail(
            request=req, entry_id=999, db=db, auth_result=user
        )
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_found(self):
        from internal.routes.knowledge import knowledge_validation_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry.validation_details = {"verdict": "accept", "steps": []}
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await knowledge_validation_detail(request=req, entry_id=1, db=db, auth_result=user)
            mock_templates.TemplateResponse.assert_called_once()
            ctx = mock_templates.TemplateResponse.call_args.kwargs["context"]
            assert ctx["entry"] == entry


class TestKnowledgeRevalidate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_revalidate

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_revalidate(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        from internal.routes.knowledge import knowledge_revalidate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_revalidate(request=req, entry_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_success(self):
        from internal.routes.knowledge import knowledge_revalidate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry.status = "accepted"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_revalidate(request=req, entry_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "re-triggered" in result.headers.get("location", "").lower()
        assert entry.status == "pending"

    @pytest.mark.asyncio
    async def test_dispatch_failure_still_succeeds(self, mock_celery_validation_task):
        """Revalidation completes even if task dispatch fails."""
        from internal.routes.knowledge import knowledge_revalidate

        mock_celery_validation_task.side_effect = Exception("Redis down")

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry.status = "accepted"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_revalidate(request=req, entry_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "re-triggered" in result.headers.get("location", "").lower()
        assert entry.status == "pending"


class TestKnowledgeApprove:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_approve

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_approve(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        from internal.routes.knowledge import knowledge_approve

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_approve(request=req, entry_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_success(self):
        from internal.routes.knowledge import knowledge_approve

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry.status = "needs_review"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_approve(request=req, entry_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "approved" in result.headers.get("location", "").lower()
        assert entry.status == "accepted"


class TestKnowledgeReject:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_reject

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_reject(request=req, entry_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_entry_not_found(self):
        from internal.routes.knowledge import knowledge_reject

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await knowledge_reject(request=req, entry_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "not+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_success(self):
        from internal.routes.knowledge import knowledge_reject

        req = _make_request()
        db = _make_db()
        user = _make_user()

        entry = _make_entry()
        entry.status = "needs_review"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = entry
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.knowledge.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await knowledge_reject(request=req, entry_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "rejected" in result.headers.get("location", "").lower()
        assert entry.status == "rejected"


# =========================================================================
# Knowledge List with Status Filter
# =========================================================================


class TestKnowledgeListStatusFilter:
    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={"status": "pending"})
        db = _make_db()
        user = _make_user()

        db.scalar = AsyncMock(return_value=0)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.knowledge.settings") as mock_settings,
            patch("internal.routes.knowledge.templates") as mock_templates,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.validation_enabled = True
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req,
                db=db,
                auth_result=user,
                page=1,
                search=None,
                namespace=None,
                status="pending",
            )

            ctx = mock_templates.TemplateResponse.call_args.kwargs["context"]
            assert ctx["status_filter"] == "pending"
            assert ctx["validation_enabled"] is True

    @pytest.mark.asyncio
    async def test_list_without_status_filter(self):
        from internal.routes.knowledge import knowledge_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ns_scalars = MagicMock()
        ns_scalars.all.return_value = []
        ns_result = MagicMock()
        ns_result.scalars.return_value = ns_scalars

        db.scalar = AsyncMock(return_value=0)
        entry_scalars = MagicMock()
        entry_scalars.all.return_value = []
        entry_result = MagicMock()
        entry_result.scalars.return_value = entry_scalars
        db.execute = AsyncMock(side_effect=[ns_result, entry_result])

        with (
            patch("internal.routes.knowledge.settings") as mock_settings,
            patch("internal.routes.knowledge.templates") as mock_templates,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_settings.validation_enabled = False
            mock_templates.TemplateResponse.return_value = MagicMock()

            await knowledge_list(
                request=req,
                db=db,
                auth_result=user,
                page=1,
                search=None,
                namespace=None,
                status=None,
            )

            ctx = mock_templates.TemplateResponse.call_args.kwargs["context"]
            assert ctx["status_filter"] is None
            assert ctx["validation_enabled"] is False


# =========================================================================
# Knowledge Create with Validation
# =========================================================================


class TestKnowledgeCreateValidation:
    @pytest.mark.asyncio
    async def test_create_with_validation_enabled(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        with (
            patch("internal.routes.knowledge.get_embedding_service", return_value=None),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.validation_enabled = True
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "validation+pending" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_create_dispatch_failure_still_succeeds(self, mock_celery_validation_task):
        """Entry is created even if task dispatch fails."""
        from internal.routes.knowledge import knowledge_create

        mock_celery_validation_task.side_effect = Exception("Redis down")

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        with (
            patch("internal.routes.knowledge.get_embedding_service", return_value=None),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.validation_enabled = True
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "validation+pending" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_create_with_validation_disabled(self):
        from internal.routes.knowledge import knowledge_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = _make_namespace()
        db.execute = AsyncMock(return_value=ns_result)

        with (
            patch("internal.routes.knowledge.get_embedding_service", return_value=None),
            patch("internal.routes.knowledge.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.validation_enabled = False
            result = await knowledge_create(
                request=req,
                question="Q?",
                answer="A.",
                namespace_id=1,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "created+successfully" in result.headers.get("location", "")


class TestKnowledgeGenerateStatus:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        redirect = RedirectResponse(url="/auth/login")
        result = await knowledge_generate_status(
            request=req,
            task_id="test-task-123",
            auth_result=redirect,
        )
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_pending_state(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        user = _make_user()

        mock_async_result = MagicMock()
        mock_async_result.state = "PENDING"

        with patch("internal.celery.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result
            result = await knowledge_generate_status(
                request=req, task_id="task-123", auth_result=user
            )

        assert result.status_code == 200
        assert b'"PENDING"' in result.body

    @pytest.mark.asyncio
    async def test_progress_state(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        user = _make_user()

        mock_async_result = MagicMock()
        mock_async_result.state = "PROGRESS"
        mock_async_result.info = {"step": "embedding", "current": 2, "total": 5}

        with patch("internal.celery.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result
            result = await knowledge_generate_status(
                request=req, task_id="task-123", auth_result=user
            )

        assert result.status_code == 200
        assert b"PROGRESS" in result.body
        assert b"embedding" in result.body

    @pytest.mark.asyncio
    async def test_success_state(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        user = _make_user()

        mock_async_result = MagicMock()
        mock_async_result.state = "SUCCESS"
        mock_async_result.result = {
            "created_count": 3,
            "entry_ids": [1, 2, 3],
            "namespace_slug": "general",
        }

        with patch("internal.celery.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result
            result = await knowledge_generate_status(
                request=req, task_id="task-123", auth_result=user
            )

        assert result.status_code == 200
        assert b"SUCCESS" in result.body
        assert b"created_count" in result.body

    @pytest.mark.asyncio
    async def test_failure_state(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        user = _make_user()

        mock_async_result = MagicMock()
        mock_async_result.state = "FAILURE"
        mock_async_result.result = Exception("Task failed")

        with patch("internal.celery.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result
            result = await knowledge_generate_status(
                request=req, task_id="task-123", auth_result=user
            )

        assert result.status_code == 200
        assert b"FAILURE" in result.body
        assert b"Task failed" in result.body

    @pytest.mark.asyncio
    async def test_started_state(self):
        from internal.routes.knowledge import knowledge_generate_status

        req = _make_request()
        user = _make_user()

        mock_async_result = MagicMock()
        mock_async_result.state = "STARTED"

        with patch("internal.celery.celery_app") as mock_celery:
            mock_celery.AsyncResult.return_value = mock_async_result
            result = await knowledge_generate_status(
                request=req, task_id="task-123", auth_result=user
            )

        assert result.status_code == 200
        assert b"STARTED" in result.body


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_default_namespace_slug(self):
        from internal.routes.knowledge import DEFAULT_NAMESPACE_SLUG

        assert DEFAULT_NAMESPACE_SLUG == "general"
