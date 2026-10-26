# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/schemas/."""

from team.schemas import (
    TeamCreate,
    TeamUpdate,
)


class TestTeamSchemas:
    def test_team_create_valid(self):
        data = TeamCreate(name="Engineering", slug="engineering")
        assert data.name == "Engineering"
        assert data.slug == "engineering"

    def test_team_update_partial(self):
        data = TeamUpdate(is_active=False)
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"is_active": False}
