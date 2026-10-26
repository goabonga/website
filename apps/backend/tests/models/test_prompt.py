# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.models.prompt.SystemPrompt."""

from unittest.mock import MagicMock

from backend.models.prompt import SystemPrompt


def _make_prompt(
    is_default: bool = False,
    required_scopes: list[str] | None = None,
    versions: list | None = None,
) -> MagicMock:
    """Create a mock SystemPrompt with real methods bound from the class."""
    prompt = MagicMock()
    prompt.is_default = is_default
    prompt.required_scopes = required_scopes
    prompt.versions = versions or []
    prompt.is_accessible = SystemPrompt.is_accessible.__get__(prompt)
    prompt.get_current_version = SystemPrompt.get_current_version.__get__(prompt)
    prompt.get_specificity = SystemPrompt.get_specificity.__get__(prompt)
    return prompt


def _make_version(is_current: bool = False) -> MagicMock:
    """Create a mock SystemPromptVersion."""
    version = MagicMock()
    version.is_current = is_current
    return version


class TestSystemPromptIsAccessible:
    """Tests for SystemPrompt.is_accessible."""

    def test_default_prompt_always_accessible(self):
        """Default prompt is always accessible regardless of scopes."""
        prompt = _make_prompt(is_default=True, required_scopes=["admin"])
        assert prompt.is_accessible(user_scopes=None) is True

    def test_no_required_scopes_always_accessible(self):
        """Prompt without required_scopes is accessible to everyone."""
        prompt = _make_prompt(is_default=False, required_scopes=None)
        assert prompt.is_accessible(user_scopes=None) is True

    def test_required_scopes_with_matching_user_scopes(self):
        """Prompt with required_scopes is accessible when user has all of them."""
        prompt = _make_prompt(required_scopes=["admin", "read"])
        assert prompt.is_accessible(user_scopes={"admin", "read", "write"}) is True

    def test_required_scopes_with_no_user_scopes_returns_false(self):
        """Prompt with required_scopes returns False when user_scopes is None."""
        prompt = _make_prompt(required_scopes=["admin"])
        assert prompt.is_accessible(user_scopes=None) is False

    def test_required_scopes_with_missing_scopes_returns_false(self):
        """Prompt with required_scopes returns False when user is missing scopes."""
        prompt = _make_prompt(required_scopes=["admin", "superuser"])
        assert prompt.is_accessible(user_scopes={"admin"}) is False


class TestSystemPromptGetCurrentVersion:
    """Tests for SystemPrompt.get_current_version."""

    def test_returns_current_version(self):
        """get_current_version returns the version where is_current=True."""
        v1 = _make_version(is_current=False)
        v2 = _make_version(is_current=True)
        v3 = _make_version(is_current=False)
        prompt = _make_prompt(versions=[v1, v2, v3])

        result = prompt.get_current_version()
        assert result is v2

    def test_returns_none_if_none_current(self):
        """get_current_version returns None if no version has is_current=True."""
        v1 = _make_version(is_current=False)
        v2 = _make_version(is_current=False)
        prompt = _make_prompt(versions=[v1, v2])

        result = prompt.get_current_version()
        assert result is None


class TestSystemPromptGetSpecificity:
    """Tests for SystemPrompt.get_specificity."""

    def test_returns_len_of_required_scopes(self):
        """get_specificity returns the number of required_scopes."""
        prompt = _make_prompt(required_scopes=["admin", "read", "write"])
        assert prompt.get_specificity() == 3

    def test_returns_zero_if_no_required_scopes(self):
        """get_specificity returns 0 if required_scopes is None."""
        prompt = _make_prompt(required_scopes=None)
        assert prompt.get_specificity() == 0
