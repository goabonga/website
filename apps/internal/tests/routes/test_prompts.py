# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for prompts routes."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse
from internal.auth.models import User


def _make_user():
    return User(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        email="test@example.com",
        name="Test User",
        scopes=["prompts:read", "prompts:write", "prompts:delete"],
    )


def _make_request(query_params=None):
    req = MagicMock()
    req.query_params = query_params or {}
    req.headers = {}
    return req


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _make_prompt(id=1, slug="test-prompt", name="Test Prompt", is_default=False):
    p = SimpleNamespace(
        id=id,
        slug=slug,
        name=name,
        description="A test prompt",
        is_default=is_default,
        required_scopes=None,
        versions=[],
    )
    p.get_current_version = MagicMock(return_value=None)
    return p


def _make_version(id=1, prompt_id=1, version=1, content="Hello", is_current=True):
    return SimpleNamespace(
        id=id,
        prompt_id=prompt_id,
        version=version,
        content=content,
        is_current=is_current,
        metadata_={},
    )


# =========================================================================
# ensure_default_prompt
# =========================================================================


@pytest.mark.asyncio
class TestEnsureDefaultPrompt:
    async def test_returns_existing_default(self):
        from internal.routes.prompts import ensure_default_prompt

        db = _make_db()
        existing = _make_prompt(is_default=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        result = await ensure_default_prompt(db)

        assert result is existing
        db.add.assert_not_called()

    async def test_creates_default_when_missing(self):
        from internal.routes.prompts import ensure_default_prompt

        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        await ensure_default_prompt(db)

        assert db.add.call_count == 2  # prompt + version
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()


# =========================================================================
# get_generator_service
# =========================================================================


class TestGetGeneratorService:
    def test_returns_none_when_no_api_key(self):
        from internal.routes.prompts import get_generator_service

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = get_generator_service()
            assert result is None

    def test_returns_service_when_api_key_set(self):
        from internal.routes.prompts import get_generator_service

        with (
            patch("internal.routes.prompts.settings") as mock_settings,
            patch("internal.services.prompt_generator.settings"),
            patch("internal.services.prompt_generator.AsyncOpenAI"),
        ):
            mock_settings.openai_api_key = "sk-test"
            result = get_generator_service()
            assert result is not None


# =========================================================================
# prompt_generate_form
# =========================================================================


@pytest.mark.asyncio
class TestPromptGenerateForm:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_generate_form

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_generate_form(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_no_openai_key(self):
        from internal.routes.prompts import prompt_generate_form

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            result = await prompt_generate_form(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "not+configured" in result.headers.get("location", "")

    async def test_success(self):
        from internal.routes.prompts import prompt_generate_form

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            mock_templates.TemplateResponse.return_value = MagicMock()
            await prompt_generate_form(request=req, db=db, auth_result=user)

            mock_templates.TemplateResponse.assert_called_once()


# =========================================================================
# prompt_generate
# =========================================================================


@pytest.mark.asyncio
class TestPromptGenerate:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_generate(
            request=req,
            description="test",
            tone="professional",
            focus_areas="",
            constraints="",
            required_scopes="",
            is_default=False,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_no_generator(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()

        with patch("internal.routes.prompts.get_generator_service", return_value=None):
            result = await prompt_generate(
                request=req,
                description="test description that is long enough",
                tone="professional",
                focus_areas="",
                constraints="",
                required_scopes="",
                is_default=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "not+configured" in result.headers.get("location", "")

    async def test_description_too_short(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()
        mock_gen = MagicMock()

        with patch("internal.routes.prompts.get_generator_service", return_value=mock_gen):
            result = await prompt_generate(
                request=req,
                description="short",
                tone="professional",
                focus_areas="",
                constraints="",
                required_scopes="",
                is_default=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "too+short" in result.headers.get("location", "")

    async def test_generation_returns_none(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()
        mock_gen = MagicMock()
        mock_gen.generate_prompt = AsyncMock(return_value=None)

        with patch("internal.routes.prompts.get_generator_service", return_value=mock_gen):
            result = await prompt_generate(
                request=req,
                description="A detailed description of what this prompt should do for testing",
                tone="professional",
                focus_areas="",
                constraints="",
                required_scopes="",
                is_default=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Failed+to+generate" in result.headers.get("location", "")

    async def test_generation_success(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()
        mock_gen = MagicMock()
        mock_gen.generate_prompt = AsyncMock(
            return_value={
                "content": "Generated content",
                "name": "Generated Prompt",
                "slug": "generated-prompt",
                "description": "A generated prompt",
            }
        )

        with (
            patch("internal.routes.prompts.get_generator_service", return_value=mock_gen),
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_generate(
                request=req,
                description="A detailed description of what this prompt should do for testing",
                tone="formal",
                focus_areas="code review, testing",
                constraints="keep it brief",
                required_scopes="prompts:read",
                is_default=True,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        loc = result.headers.get("location", "")
        assert "generated=1" in loc
        assert "is_default=1" in loc

    async def test_generation_exception(self):
        from internal.routes.prompts import prompt_generate

        req = _make_request()
        db = _make_db()
        user = _make_user()
        mock_gen = MagicMock()
        mock_gen.generate_prompt = AsyncMock(side_effect=RuntimeError("API down"))

        with patch("internal.routes.prompts.get_generator_service", return_value=mock_gen):
            result = await prompt_generate(
                request=req,
                description="A detailed description of what this prompt should do for testing",
                tone="professional",
                focus_areas="",
                constraints="",
                required_scopes="",
                is_default=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Generation+failed" in result.headers.get("location", "")


# =========================================================================
# prompt_list
# =========================================================================


@pytest.mark.asyncio
class TestPromptList:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_list

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_list(request=req, page=1, search=None, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_success(self):
        from internal.routes.prompts import prompt_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        # ensure_default_prompt check
        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = _make_prompt(is_default=True)

        # count query
        count_result = 5

        # paginated results
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [_make_prompt()]
        list_result = MagicMock()
        list_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[default_result, list_result])
        db.scalar = AsyncMock(return_value=count_result)

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = "sk-test"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await prompt_list(request=req, page=1, search=None, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 5
            assert call_kwargs["context"]["openai_configured"] is True

    async def test_with_search(self):
        from internal.routes.prompts import prompt_list

        req = _make_request()
        db = _make_db()
        user = _make_user()

        default_result = MagicMock()
        default_result.scalar_one_or_none.return_value = _make_prompt(is_default=True)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result = MagicMock()
        list_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[default_result, list_result])
        db.scalar = AsyncMock(return_value=0)

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_settings.openai_api_key = ""
            mock_templates.TemplateResponse.return_value = MagicMock()

            await prompt_list(request=req, page=1, search="test", db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["search"] == "test"
            assert call_kwargs["context"]["openai_configured"] is False


# =========================================================================
# prompt_new
# =========================================================================


@pytest.mark.asyncio
class TestPromptNew:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_new

        req = _make_request()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_new(request=req, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_success(self):
        from internal.routes.prompts import prompt_new

        req = _make_request(
            query_params={
                "generated": "1",
                "name": "AI Prompt",
                "slug": "ai",
                "description": "desc",
                "content": "Hello",
            }
        )
        user = _make_user()

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await prompt_new(request=req, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["generated"] is True
            assert call_kwargs["context"]["prefill_name"] == "AI Prompt"


# =========================================================================
# prompt_create
# =========================================================================


@pytest.mark.asyncio
class TestPromptCreate:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_create(
            request=req,
            slug="s",
            name="n",
            content="c",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{}",
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_invalid_metadata_json(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result = await prompt_create(
            request=req,
            slug="test",
            name="Test",
            content="Hello",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{bad json",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Invalid+JSON" in result.headers.get("location", "")

    async def test_slug_already_exists(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = _make_prompt()
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_create(
            request=req,
            slug="existing",
            name="Test",
            content="Hello",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{}",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "already+exists" in result.headers.get("location", "")

    async def test_create_success(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_create(
                request=req,
                slug="  New-Prompt  ",
                name="  New Prompt  ",
                content="You are a helpful assistant",
                description="  A description  ",
                required_scopes="scope1, scope2",
                is_default=False,
                metadata_json='{"key": "val"}',
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")
        assert db.add.call_count == 2  # prompt + version
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_create_as_default(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_create(
                request=req,
                slug="default-new",
                name="New Default",
                content="Content",
                description="",
                required_scopes="",
                is_default=True,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        # Should have called execute twice: once for slug check, once to unset default
        assert db.execute.await_count >= 2

    async def test_create_empty_metadata(self):
        from internal.routes.prompts import prompt_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_create(
                request=req,
                slug="test",
                name="Test",
                content="Content",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


# =========================================================================
# prompt_detail
# =========================================================================


@pytest.mark.asyncio
class TestPromptDetail:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_detail

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_detail(request=req, prompt_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_not_found(self):
        from internal.routes.prompts import prompt_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_detail(request=req, prompt_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_found(self):
        from internal.routes.prompts import prompt_detail

        req = _make_request(query_params={"success": "done"})
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt()
        ver = _make_version()
        prompt.get_current_version = MagicMock(return_value=ver)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await prompt_detail(request=req, prompt_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["prompt"] is prompt
            assert call_kwargs["context"]["current_version"] is ver


# =========================================================================
# prompt_edit
# =========================================================================


@pytest.mark.asyncio
class TestPromptEdit:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_edit

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_edit(request=req, prompt_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_not_found(self):
        from internal.routes.prompts import prompt_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_edit(request=req, prompt_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_found(self):
        from internal.routes.prompts import prompt_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt()
        ver = _make_version()
        prompt.get_current_version = MagicMock(return_value=ver)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.prompts.templates") as mock_templates,
            patch("internal.routes.prompts.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await prompt_edit(request=req, prompt_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["is_edit"] is True
            assert call_kwargs["context"]["current_version"] is ver


# =========================================================================
# prompt_update
# =========================================================================


@pytest.mark.asyncio
class TestPromptUpdate:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_update(
            request=req,
            prompt_id=1,
            slug="s",
            name="n",
            content="c",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{}",
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_not_found(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_update(
            request=req,
            prompt_id=999,
            slug="test",
            name="Test",
            content="Hello",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{}",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_invalid_metadata_json(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_update(
            request=req,
            prompt_id=1,
            slug="test-prompt",
            name="Test",
            content="Hello",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{bad",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Invalid+JSON" in result.headers.get("location", "")

    async def test_slug_conflict(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt(id=1, slug="old-slug")
        prompt_result = MagicMock()
        prompt_result.scalar_one_or_none.return_value = prompt

        existing = _make_prompt(id=2, slug="new-slug")
        conflict_result = MagicMock()
        conflict_result.scalar_one_or_none.return_value = existing

        db.execute = AsyncMock(side_effect=[prompt_result, conflict_result])

        result = await prompt_update(
            request=req,
            prompt_id=1,
            slug="new-slug",
            name="Updated",
            content="Hello",
            description="",
            required_scopes="",
            is_default=False,
            metadata_json="{}",
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "already+exists" in result.headers.get("location", "")

    async def test_slug_change_no_conflict(self):
        """Covers branch 544->551: slug changes but no conflict exists."""
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Same content")
        prompt = _make_prompt(id=1, slug="old-slug")
        prompt.get_current_version = MagicMock(return_value=ver)

        prompt_result = MagicMock()
        prompt_result.scalar_one_or_none.return_value = prompt

        # No conflict: scalar_one_or_none returns None
        no_conflict_result = MagicMock()
        no_conflict_result.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[prompt_result, no_conflict_result])

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="new-slug",
                name="Updated",
                content="Same content",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        assert prompt.slug == "new-slug"

    async def test_update_same_slug_no_content_change(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Same content")
        prompt = _make_prompt(id=1, slug="test-prompt")
        prompt.get_current_version = MagicMock(return_value=ver)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Updated Name",
                content="Same content",
                description="desc",
                required_scopes="scope1",
                is_default=False,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        # No new version added (content unchanged)
        db.add.assert_not_called()

    async def test_update_with_content_change(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Old content", version=2)
        prompt = _make_prompt(id=1, slug="test-prompt")
        prompt.get_current_version = MagicMock(return_value=ver)
        prompt.versions = [
            _make_version(version=1),
            _make_version(version=2),
        ]

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Updated",
                content="New content",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.add.assert_called_once()  # New version created

    async def test_update_content_change_with_out_of_order_versions(self):
        """Covers branch 569->568: v.version <= max_version during iteration."""
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Old content", version=3)
        prompt = _make_prompt(id=1, slug="test-prompt")
        prompt.get_current_version = MagicMock(return_value=ver)
        # Out-of-order: after v3 sets max=3, v1 has 1 <= 3 (False branch)
        prompt.versions = [
            _make_version(version=3),
            _make_version(version=1),
        ]

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Updated",
                content="New content",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.add.assert_called_once()

    async def test_update_no_current_version(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt(id=1, slug="test-prompt")
        prompt.get_current_version = MagicMock(return_value=None)
        prompt.versions = []

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Updated",
                content="New content",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        db.add.assert_called_once()  # New version created

    async def test_update_set_default(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Same")
        prompt = _make_prompt(id=1, slug="test-prompt", is_default=False)
        prompt.get_current_version = MagicMock(return_value=ver)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Updated",
                content="Same",
                description="",
                required_scopes="",
                is_default=True,
                metadata_json="{}",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        # execute called: find prompt + unset existing defaults
        assert db.execute.await_count >= 2

    async def test_update_empty_metadata(self):
        from internal.routes.prompts import prompt_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(content="Same")
        prompt = _make_prompt(id=1, slug="test-prompt")
        prompt.get_current_version = MagicMock(return_value=ver)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_update(
                request=req,
                prompt_id=1,
                slug="test-prompt",
                name="Test",
                content="Same",
                description="",
                required_scopes="",
                is_default=False,
                metadata_json="",
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


# =========================================================================
# prompt_activate_version
# =========================================================================


@pytest.mark.asyncio
class TestPromptActivateVersion:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_activate_version

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_activate_version(
            request=req,
            prompt_id=1,
            version_id=1,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_version_not_found(self):
        from internal.routes.prompts import prompt_activate_version

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_activate_version(
            request=req,
            prompt_id=1,
            version_id=999,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_activate_success(self):
        from internal.routes.prompts import prompt_activate_version

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(id=5, version=3, is_current=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ver
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_activate_version(
                request=req,
                prompt_id=1,
                version_id=5,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Version+3+activated" in result.headers.get("location", "")
        assert ver.is_current is True
        db.commit.assert_awaited_once()


# =========================================================================
# prompt_version_delete
# =========================================================================


@pytest.mark.asyncio
class TestPromptVersionDelete:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_version_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_version_delete(
            request=req,
            prompt_id=1,
            version_id=1,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_version_not_found(self):
        from internal.routes.prompts import prompt_version_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_version_delete(
            request=req,
            prompt_id=1,
            version_id=999,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_cannot_delete_current(self):
        from internal.routes.prompts import prompt_version_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(is_current=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ver
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_version_delete(
            request=req,
            prompt_id=1,
            version_id=1,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Cannot+delete+the+current" in result.headers.get("location", "")

    async def test_delete_success(self):
        from internal.routes.prompts import prompt_version_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ver = _make_version(id=5, version=2, is_current=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ver
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_version_delete(
                request=req,
                prompt_id=1,
                version_id=5,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "Version+2+deleted" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(ver)
        db.commit.assert_awaited_once()


# =========================================================================
# prompt_versions_bulk_delete
# =========================================================================


@pytest.mark.asyncio
class TestPromptVersionsBulkDelete:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_versions_bulk_delete(
            request=req,
            prompt_id=1,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    async def test_no_ids_selected(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await prompt_versions_bulk_delete(
            request=req,
            prompt_id=1,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "No+versions+selected" in result.headers.get("location", "")

    async def test_invalid_ids(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["not-int"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await prompt_versions_bulk_delete(
            request=req,
            prompt_id=1,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "Invalid" in result.headers.get("location", "")

    async def test_no_versions_found(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_versions_bulk_delete(
            request=req,
            prompt_id=1,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "No+versions+found" in result.headers.get("location", "")

    async def test_skips_current_version(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        current_ver = _make_version(id=1, is_current=True)
        old_ver = _make_version(id=2, is_current=False)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [current_ver, old_ver]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_versions_bulk_delete(
                request=req,
                prompt_id=1,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        loc = result.headers.get("location", "")
        assert "1+version(s)+deleted" in loc
        assert "1+skipped" in loc
        db.delete.assert_awaited_once_with(old_ver)

    async def test_comma_separated_selection(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        # The detail page sends the whole selection as one comma-separated value
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["2,3"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [
            _make_version(id=2, is_current=False),
            _make_version(id=3, is_current=False),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_versions_bulk_delete(
                request=req, prompt_id=1, db=db, auth_result=_make_user()
            )

        assert "2+version(s)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2

    async def test_delete_all_non_current(self):
        from internal.routes.prompts import prompt_versions_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        v1 = _make_version(id=1, is_current=False)
        v2 = _make_version(id=2, is_current=False)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [v1, v2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_versions_bulk_delete(
                request=req,
                prompt_id=1,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "2+version(s)+deleted+successfully" in result.headers.get("location", "")


# =========================================================================
# prompt_bulk_delete
# =========================================================================


@pytest.mark.asyncio
class TestPromptBulkDelete:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_bulk_delete(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_no_ids_selected(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await prompt_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+prompts+selected" in result.headers.get("location", "")

    async def test_invalid_ids(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["not-int"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await prompt_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid" in result.headers.get("location", "")

    async def test_no_prompts_found(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+prompts+found" in result.headers.get("location", "")

    async def test_skips_default(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        default_p = _make_prompt(id=1, is_default=True)
        other_p = _make_prompt(id=2, is_default=False)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [default_p, other_p]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_bulk_delete(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        loc = result.headers.get("location", "")
        assert "1+prompt(s)+deleted" in loc
        assert "1+skipped" in loc
        db.delete.assert_awaited_once_with(other_p)

    async def test_comma_separated_selection(self):
        from internal.routes.prompts import prompt_bulk_delete

        # The list page sends the whole selection as one comma-separated value
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1,2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [_make_prompt(id=1), _make_prompt(id=2)]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_bulk_delete(request=req, db=db, auth_result=_make_user())

        assert "2+prompt(s)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2

    async def test_delete_all_non_default(self):
        from internal.routes.prompts import prompt_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        p1 = _make_prompt(id=1, is_default=False)
        p2 = _make_prompt(id=2, is_default=False)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [p1, p2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_bulk_delete(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "2+prompt(s)+deleted+successfully" in result.headers.get("location", "")


# =========================================================================
# prompt_delete
# =========================================================================


@pytest.mark.asyncio
class TestPromptDelete:
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.prompts import prompt_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await prompt_delete(request=req, prompt_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    async def test_not_found(self):
        from internal.routes.prompts import prompt_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_delete(request=req, prompt_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    async def test_cannot_delete_default(self):
        from internal.routes.prompts import prompt_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt(is_default=True)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        result = await prompt_delete(request=req, prompt_id=1, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Cannot+delete" in result.headers.get("location", "")

    async def test_delete_success(self):
        from internal.routes.prompts import prompt_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        prompt = _make_prompt(is_default=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = prompt
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.prompts.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await prompt_delete(request=req, prompt_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(prompt)
        db.commit.assert_awaited_once()


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_default_prompt_slug(self):
        from internal.routes.prompts import DEFAULT_PROMPT_SLUG

        assert DEFAULT_PROMPT_SLUG == "default"
