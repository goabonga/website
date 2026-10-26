# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for Pydantic schema validation. Pure tests, no mocks needed."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from knowledge.models import Collection
from knowledge.models.enums import OwnerType
from knowledge.schemas.collection import CollectionCreate, CollectionResponse, CollectionUpdate


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


class TestCollectionResponse:
    def _collection(self, **overrides):
        now = datetime.now(UTC)
        attrs = {
            "id": uuid4(),
            "owner_type": OwnerType.USER,
            "owner_id": uuid4(),
            "name": "Docs",
            "slug": "docs",
            "description": None,
            "embedding_model": "text-embedding-3-small",
            "dimension": 1536,
            "metadata_schema": None,
            "document_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        attrs.update(overrides)
        return Collection(**attrs)

    def test_personal_collection_has_no_tenant(self):
        response = CollectionResponse.model_validate(self._collection())
        assert response.tenant_id is None

    def test_organization_collection_exposes_tenant(self):
        org_id = uuid4()
        collection = self._collection(
            owner_type=OwnerType.ORGANIZATION, owner_id=org_id, organization_id=org_id
        )
        response = CollectionResponse.model_validate(collection)
        assert response.tenant_id == org_id
