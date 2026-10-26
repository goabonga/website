# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.prompts.service.PromptService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.prompts.service import DEFAULT_FALLBACK_PROMPT


@pytest.fixture
def mock_session():
    """Return a mocked AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_cache():
    """Return a mocked prompt_cache."""
    cache = AsyncMock()
    cache.get_for_scopes = AsyncMock(return_value=None)
    cache.set_for_scopes = AsyncMock()
    cache.invalidate = AsyncMock()
    return cache


@pytest.fixture
def prompt_service(mock_session, mock_cache):
    """Create a PromptService with mocked dependencies."""
    with patch("backend.prompts.service.prompt_cache", mock_cache):
        from backend.prompts.service import PromptService

        service = PromptService(session=mock_session)
        service._mock_cache = mock_cache
        yield service


def _make_prompt(
    prompt_id,
    slug,
    name,
    is_default=False,
    required_scopes=None,
    current_version_content=None,
):
    """Helper to create a mock SystemPrompt."""
    prompt = MagicMock()
    prompt.id = prompt_id
    prompt.slug = slug
    prompt.name = name
    prompt.is_default = is_default
    prompt.required_scopes = required_scopes

    # Replicate is_accessible logic
    def is_accessible(user_scopes):
        if is_default:
            return True
        if not required_scopes:
            return True
        if user_scopes is None:
            return False
        return set(required_scopes).issubset(user_scopes)

    prompt.is_accessible = is_accessible
    prompt.get_specificity = lambda: len(required_scopes) if required_scopes else 0

    # Mock current version
    if current_version_content is not None:
        version = MagicMock()
        version.content = current_version_content
        version.version = 1
        version.is_current = True
        prompt.get_current_version.return_value = version
    else:
        prompt.get_current_version.return_value = None

    return prompt


class TestGetPromptForScopes:
    """Tests for get_prompt_for_scopes."""

    async def test_cache_hit_returns_cached(self, mock_session, mock_cache):
        """When cache has a value for the scopes, it should be returned directly."""
        mock_cache.get_for_scopes.return_value = "cached prompt content"

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes({"openid"})

        assert result == "cached prompt content"
        mock_session.execute.assert_not_awaited()

    async def test_selects_most_specific_prompt(self, mock_session, mock_cache):
        """Should select the prompt with the most required scopes that match."""
        default_prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content="Default content",
        )
        specific_prompt = _make_prompt(
            2,
            "admin",
            "Admin",
            is_default=False,
            required_scopes=["admin:read", "admin:write"],
            current_version_content="Admin content",
        )
        general_prompt = _make_prompt(
            3,
            "general",
            "General",
            is_default=False,
            required_scopes=["openid"],
            current_version_content="General content",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            default_prompt,
            specific_prompt,
            general_prompt,
        ]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes({"openid", "admin:read", "admin:write"})

        assert result == "Admin content"

    async def test_falls_back_to_default(self, mock_session, mock_cache):
        """When no specific prompt matches, should fall back to the default prompt."""
        default_prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content="Default content",
        )
        scoped_prompt = _make_prompt(
            2,
            "admin",
            "Admin",
            is_default=False,
            required_scopes=["admin:read"],
            current_version_content="Admin content",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            default_prompt,
            scoped_prompt,
        ]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            # User without admin scope; only the default prompt is accessible as non-default
            result = await service.get_prompt_for_scopes({"openid"})

        assert result == "Default content"

    async def test_no_prompts_returns_fallback_constant(self, mock_session, mock_cache):
        """When no prompts exist in DB, should return DEFAULT_FALLBACK_PROMPT."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes({"openid"})

        assert result == DEFAULT_FALLBACK_PROMPT

    async def test_no_current_version_returns_fallback(self, mock_session, mock_cache):
        """When the selected prompt has no current version, should return fallback."""
        prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content=None,  # No current version
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [prompt]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes(None)

        assert result == DEFAULT_FALLBACK_PROMPT

    async def test_db_error_returns_fallback(self, mock_session, mock_cache):
        """When a database error occurs, should return the fallback prompt."""
        mock_session.execute.side_effect = Exception("DB connection lost")

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes({"openid"})

        assert result == DEFAULT_FALLBACK_PROMPT

    async def test_no_accessible_and_no_default_returns_fallback(self, mock_session, mock_cache):
        """When prompts exist but none are accessible and no default, return fallback."""
        scoped_prompt = _make_prompt(
            1,
            "admin",
            "Admin",
            is_default=False,
            required_scopes=["admin:write"],
            current_version_content="Admin content",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [scoped_prompt]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            # User has no scopes, and the only prompt requires admin:write
            result = await service.get_prompt_for_scopes(None)

        assert result == DEFAULT_FALLBACK_PROMPT


class TestGetPromptBySlug:
    """Tests for get_prompt_by_slug."""

    async def test_found(self, mock_session, mock_cache):
        """get_prompt_by_slug() should return the prompt when found."""
        prompt = _make_prompt(1, "general", "General", current_version_content="content")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prompt
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_by_slug("general")

        assert result == prompt
        assert result.slug == "general"


class TestGetDefaultPrompt:
    """Tests for get_default_prompt."""

    async def test_found(self, mock_session, mock_cache):
        """get_default_prompt() should return the default prompt when it exists."""
        prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content="Default content",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = prompt
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_default_prompt()

        assert result == prompt
        assert result.is_default is True


class TestCreatePrompt:
    """Tests for create_prompt."""

    async def test_creates_prompt_with_version(self, mock_session, mock_cache):
        """create_prompt() should create a prompt and its initial version."""
        mock_session.flush.return_value = None

        # Mock the prompt object that gets created
        _make_prompt(
            1,
            "new-prompt",
            "New Prompt",
            current_version_content="Initial content",
        )
        mock_session.refresh.side_effect = lambda obj: (
            setattr(obj, "id", 1) if hasattr(obj, "slug") else None
        )

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            await service.create_prompt(
                slug="new-prompt",
                name="New Prompt",
                content="Initial content",
                description="A test prompt",
                is_default=False,
            )

        # Verify session interactions: add was called for both prompt and version
        assert mock_session.add.call_count == 2
        mock_session.flush.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        mock_cache.invalidate.assert_awaited_once()


class TestGetPromptForScopesAdditional:
    """Additional tests for get_prompt_for_scopes covering more branches."""

    async def test_selects_non_default_over_default(self, mock_session, mock_cache):
        """When a non-default accessible prompt exists, it should be selected over the default."""
        default_prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content="Default content",
        )
        non_default_prompt = _make_prompt(
            2,
            "general",
            "General",
            is_default=False,
            required_scopes=["openid"],
            current_version_content="General content",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            default_prompt,
            non_default_prompt,
        ]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.get_prompt_for_scopes({"openid"})

        assert result == "General content"

    async def test_caches_result(self, mock_session, mock_cache):
        """get_prompt_for_scopes() should cache the selected prompt content via set_for_scopes."""
        prompt = _make_prompt(
            1,
            "default",
            "Default",
            is_default=True,
            current_version_content="Default content",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [prompt]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            scopes = {"openid"}
            result = await service.get_prompt_for_scopes(scopes)

        assert result == "Default content"
        mock_cache.set_for_scopes.assert_awaited_once_with(scopes, "Default content")


class TestCreatePromptAdditional:
    """Additional tests for create_prompt."""

    async def test_create_prompt_unsets_existing_default(self, mock_session, mock_cache):
        """create_prompt(is_default=True) should unset existing default prompts."""
        mock_session.flush.return_value = None

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            await service.create_prompt(
                slug="new-default",
                name="New Default",
                content="Content",
                is_default=True,
            )

        # execute should have been called to unset existing defaults
        mock_session.execute.assert_awaited()
        mock_session.commit.assert_awaited_once()


class TestCreateVersion:
    """Tests for create_version."""

    async def test_create_version(self, mock_session, mock_cache):
        """create_version() should create a new version with bumped version number."""
        # Mock current max version
        max_version_result = MagicMock()
        max_version_result.scalar_one_or_none.return_value = 2
        # Mock the update (unset current) - returns execute result
        update_result = MagicMock()

        mock_session.execute.side_effect = [max_version_result, update_result]

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            await service.create_version(
                prompt_id=1,
                content="New version content",
            )

        # Should have added a version
        mock_session.add.assert_called_once()
        added_version = mock_session.add.call_args[0][0]
        assert added_version.version == 3  # current_max (2) + 1
        assert added_version.is_current is True
        assert added_version.content == "New version content"

        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        mock_cache.invalidate.assert_awaited_once()


class TestSetCurrentVersion:
    """Tests for set_current_version."""

    async def test_set_current_version(self, mock_session, mock_cache):
        """set_current_version() should set the specified version as current."""
        mock_version = MagicMock()
        mock_version.id = 5
        mock_version.prompt_id = 1
        mock_version.version = 2
        mock_version.is_current = False

        # First call: find version by id; second: update statement
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = mock_version
        update_result = MagicMock()

        mock_session.execute.side_effect = [find_result, update_result]

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.set_current_version(5)

        assert result is mock_version
        assert mock_version.is_current is True
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()
        mock_cache.invalidate.assert_awaited_once()

    async def test_set_current_version_not_found(self, mock_session, mock_cache):
        """set_current_version() should return None when version not found."""
        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = find_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.set_current_version(999)

        assert result is None


class TestRollbackToVersion:
    """Tests for rollback_to_version."""

    async def test_rollback_to_version(self, mock_session, mock_cache):
        """rollback_to_version() should delegate to set_current_version."""
        mock_version = MagicMock()
        mock_version.id = 3
        mock_version.prompt_id = 1
        mock_version.version = 1
        mock_version.is_current = False

        find_result = MagicMock()
        find_result.scalar_one_or_none.return_value = mock_version
        update_result = MagicMock()
        mock_session.execute.side_effect = [find_result, update_result]

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.rollback_to_version(3)

        assert result is mock_version
        assert mock_version.is_current is True


class TestListVersions:
    """Tests for list_versions."""

    async def test_list_versions(self, mock_session, mock_cache):
        """list_versions() should return a list of versions for the prompt."""
        v1 = MagicMock()
        v1.version = 1
        v2 = MagicMock()
        v2.version = 2

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [v2, v1]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.list_versions(prompt_id=1)

        assert len(result) == 2
        assert result[0].version == 2
        assert result[1].version == 1


class TestListPrompts:
    """Tests for list_prompts."""

    async def test_list_prompts(self, mock_session, mock_cache):
        """list_prompts() with no user_scopes should return all prompts."""
        p1 = _make_prompt(1, "general", "General")
        p2 = _make_prompt(2, "admin", "Admin", required_scopes=["admin"])

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [p1, p2]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.list_prompts(user_scopes=None)

        assert len(result) == 2

    async def test_list_prompts_filtered_by_scopes(self, mock_session, mock_cache):
        """list_prompts() with user_scopes should filter by accessibility."""
        p1 = _make_prompt(1, "general", "General")
        p2 = _make_prompt(2, "admin", "Admin", required_scopes=["admin:read"])

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [p1, p2]
        mock_session.execute.return_value = mock_result

        with patch("backend.prompts.service.prompt_cache", mock_cache):
            from backend.prompts.service import PromptService

            service = PromptService(session=mock_session)
            result = await service.list_prompts(user_scopes={"openid"})

        # Only p1 (general) should be accessible; p2 requires admin:read
        assert len(result) == 1
        assert result[0].slug == "general"
