# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/models/."""

from team.models import (
    Base,
)


class TestModelsImport:
    """Tests that all models are importable and correctly configured."""

    def test_base_is_importable(self):
        assert Base is not None
