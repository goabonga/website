# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/models/."""

from team.models import (
    Base,
    Team,
)


class TestModelsImport:
    """Tests that all models are importable and correctly configured."""

    def test_base_is_importable(self):
        assert Base is not None

    def test_team_tablename(self):
        assert Team.__tablename__ == "teams"


def test_all_models_registered_in_metadata():
    """All model tables should be registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "teams",
    }
    assert expected.issubset(table_names)
