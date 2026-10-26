# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.base — Base model and TimestampMixin."""

from auth.db.base import Base, TimestampMixin, convention


class TestConvention:
    def test_naming_convention_keys(self):
        assert "ix" in convention
        assert "uq" in convention
        assert "ck" in convention
        assert "fk" in convention
        assert "pk" in convention

    def test_index_pattern(self):
        assert "%(column_0_label)s" in convention["ix"]

    def test_unique_pattern(self):
        assert "%(table_name)s" in convention["uq"]

    def test_fk_pattern(self):
        assert "%(referred_table_name)s" in convention["fk"]


class TestBase:
    def test_metadata_has_naming_convention(self):
        assert Base.metadata.naming_convention is not None


class TestTimestampMixin:
    def test_has_created_at(self):
        assert hasattr(TimestampMixin, "created_at")

    def test_has_updated_at(self):
        assert hasattr(TimestampMixin, "updated_at")
