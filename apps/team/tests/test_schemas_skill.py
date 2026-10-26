# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for skill Pydantic schemas."""

import pytest
from team.schemas.skill import SkillCreate, SkillUpdate


class TestSkillCreateValidation:
    def test_valid_name(self):
        skill = SkillCreate(name="code-review", description="Review code.", content="# Review")
        assert skill.name == "code-review"

    def test_valid_name_no_hyphens(self):
        skill = SkillCreate(name="deploy", description="Deploy.", content="# Deploy")
        assert skill.name == "deploy"

    def test_valid_name_with_numbers(self):
        skill = SkillCreate(name="pdf-v2", description="PDF v2.", content="# PDF")
        assert skill.name == "pdf-v2"

    def test_invalid_name_uppercase(self):
        with pytest.raises(ValueError, match="lowercase"):
            SkillCreate(name="Code-Review", description="Review.", content="# Review")

    def test_invalid_name_starts_with_hyphen(self):
        with pytest.raises(ValueError, match="lowercase"):
            SkillCreate(name="-review", description="Review.", content="# Review")

    def test_invalid_name_ends_with_hyphen(self):
        with pytest.raises(ValueError, match="lowercase"):
            SkillCreate(name="review-", description="Review.", content="# Review")

    def test_invalid_name_consecutive_hyphens(self):
        with pytest.raises(ValueError, match="lowercase"):
            SkillCreate(name="code--review", description="Review.", content="# Review")

    def test_default_optional_fields(self):
        skill = SkillCreate(name="test", description="Test.", content="# Test")
        assert skill.license == ""
        assert skill.compatibility == ""
        assert skill.metadata == {}
        assert skill.allowed_tools == []
        assert skill.is_active is True

    def test_all_fields(self):
        skill = SkillCreate(
            name="pdf-processing",
            description="Extract text from PDFs.",
            content="# PDF\n\n1. Use pdfplumber",
            license="Apache-2.0",
            compatibility="Requires poppler",
            metadata={"author": "test", "version": "1.0"},
            allowed_tools=["file_read", "file_write"],
            is_active=False,
        )
        assert skill.license == "Apache-2.0"
        assert skill.metadata == {"author": "test", "version": "1.0"}
        assert skill.allowed_tools == ["file_read", "file_write"]
        assert skill.is_active is False


class TestSkillUpdateValidation:
    def test_all_none_by_default(self):
        update = SkillUpdate()
        assert update.name is None
        assert update.description is None
        assert update.content is None

    def test_valid_name_update(self):
        update = SkillUpdate(name="new-name")
        assert update.name == "new-name"

    def test_invalid_name_update(self):
        with pytest.raises(ValueError, match="lowercase"):
            SkillUpdate(name="BAD-NAME")

    def test_partial_update(self):
        update = SkillUpdate(description="Updated desc")
        assert update.description == "Updated desc"
        assert update.name is None
        assert update.content is None
