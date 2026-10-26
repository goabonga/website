# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.models.knowledge.KnowledgeNamespace.is_accessible."""

from unittest.mock import MagicMock

from backend.models.knowledge import KnowledgeNamespace


def _make_namespace(is_public: bool, required_scopes: list[str] | None) -> MagicMock:
    """Create a mock namespace with is_accessible bound from the real class."""
    ns = MagicMock()
    ns.is_public = is_public
    ns.required_scopes = required_scopes
    ns.is_accessible = KnowledgeNamespace.is_accessible.__get__(ns)
    return ns


class TestKnowledgeNamespaceIsAccessible:
    """Tests for KnowledgeNamespace.is_accessible."""

    def test_public_no_required_scopes_returns_true(self):
        """Public namespace with no required_scopes is always accessible."""
        ns = _make_namespace(is_public=True, required_scopes=None)
        assert ns.is_accessible(user_scopes=None) is True

    def test_public_no_required_scopes_with_user_scopes_returns_true(self):
        """Public namespace with no required_scopes is accessible even with non-None scopes."""
        ns = _make_namespace(is_public=True, required_scopes=None)
        assert ns.is_accessible(user_scopes={"openid", "profile"}) is True

    def test_non_public_anonymous_user_returns_false(self):
        """Non-public namespace with anonymous user (None scopes) returns False."""
        ns = _make_namespace(is_public=False, required_scopes=None)
        assert ns.is_accessible(user_scopes=None) is False

    def test_required_scopes_user_has_all_returns_true(self):
        """Namespace with required_scopes where user has all of them returns True."""
        ns = _make_namespace(is_public=True, required_scopes=["admin", "read"])
        assert ns.is_accessible(user_scopes={"admin", "read", "write"}) is True

    def test_required_scopes_user_missing_some_returns_false(self):
        """Namespace with required_scopes where user is missing some returns False."""
        ns = _make_namespace(is_public=True, required_scopes=["admin", "read"])
        assert ns.is_accessible(user_scopes={"read"}) is False

    def test_required_scopes_anonymous_user_returns_false(self):
        """Namespace with required_scopes and anonymous user (None scopes) returns False."""
        ns = _make_namespace(is_public=False, required_scopes=["admin"])
        assert ns.is_accessible(user_scopes=None) is False

    def test_non_public_with_scopes_no_required_scopes_returns_is_public(self):
        """Non-public namespace with user scopes but no required_scopes returns is_public (False)."""
        ns = _make_namespace(is_public=False, required_scopes=None)
        assert ns.is_accessible(user_scopes={"openid"}) is False

    def test_public_with_required_scopes_anonymous_user_returns_false(self):
        """Public namespace with required_scopes and anonymous user returns False."""
        ns = _make_namespace(is_public=True, required_scopes=["admin"])
        assert ns.is_accessible(user_scopes=None) is False
