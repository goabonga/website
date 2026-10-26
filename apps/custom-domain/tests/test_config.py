# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/config.py."""


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test default settings values."""
        from custom_domain.config import settings

        assert settings.app_name == "Custom Domain Service"
        assert isinstance(settings.docs_enabled, bool)
        assert isinstance(settings.database_echo, bool)
        assert isinstance(settings.log_level, str)

    def test_base_dir_property(self):
        """Test base_dir property returns the directory holding the package."""
        from custom_domain.config import settings

        base_dir = settings.base_dir
        assert base_dir.exists()
        assert (base_dir / "custom_domain").exists()

    def test_settings_has_required_attributes(self):
        """Test settings has all required attributes."""
        from custom_domain.config import settings

        assert hasattr(settings, "database_url")
        assert hasattr(settings, "cors_origins")
        assert hasattr(settings, "cors_methods")
