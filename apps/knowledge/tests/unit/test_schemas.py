# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Pydantic schema validation. Pure tests, no mocks needed."""

import pytest
from pydantic import ValidationError

from knowledge.schemas.collection import CollectionCreate, CollectionUpdate


class TestCollectionCreate:
    def test_valid(self):
        c = CollectionCreate(name="Test", slug="test")
        assert c.name == "Test"
        assert c.slug == "test"
        assert c.embedding_model == "text-embedding-3-small"
        assert c.dimension == 1536

    def test_slug_with_uppercase_fails(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="Test", slug="Test")

    def test_slug_with_spaces_fails(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="Test", slug="my slug")

    def test_slug_with_special_chars_fails(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="Test", slug="test_slug!")

    def test_valid_slug_with_hyphens(self):
        c = CollectionCreate(name="Test", slug="my-test-collection")
        assert c.slug == "my-test-collection"

    def test_name_empty_fails(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="", slug="test")

    def test_name_too_long_fails(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="a" * 256, slug="test")

    def test_dimension_below_min(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="Test", slug="test", dimension=0)

    def test_dimension_above_max(self):
        with pytest.raises(ValidationError):
            CollectionCreate(name="Test", slug="test", dimension=4097)

    def test_with_description(self):
        c = CollectionCreate(name="Test", slug="test", description="A description")
        assert c.description == "A description"


class TestCollectionUpdate:
    def test_empty_update_valid(self):
        u = CollectionUpdate()
        assert u.name is None
        assert u.description is None

    def test_partial_update(self):
        u = CollectionUpdate(name="New Name")
        assert u.name == "New Name"
        assert u.description is None
