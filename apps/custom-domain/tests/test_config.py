# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/config.py."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestGetCredential:
    """Tests for get_credential function."""

    def test_get_credential_from_env(self):
        """Test getting credential from environment variable."""
        from custom_domain.config import get_credential

        with patch.dict(os.environ, {"TEST_CRED": "test_value"}, clear=False):
            result = get_credential("TEST_CRED")
            assert result == "test_value"

    def test_get_credential_default(self):
        """Test getting default value when credential not found."""
        from custom_domain.config import get_credential

        with patch.dict(os.environ, {}, clear=False):
            # Remove the key if it exists
            os.environ.pop("NONEXISTENT_CRED", None)
            result = get_credential("NONEXISTENT_CRED", "default_val")
            assert result == "default_val"

    def test_get_credential_from_file(self):
        """Test getting credential from systemd credentials directory."""
        from custom_domain.config import get_credential

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create credential file
            cred_file = Path(tmpdir) / "MY_SECRET"
            cred_file.write_text("secret_from_file\n")

            with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": tmpdir}, clear=False):
                result = get_credential("MY_SECRET")
                assert result == "secret_from_file"

    def test_get_credential_file_not_exists(self):
        """Test fallback to env when credential file doesn't exist."""
        from custom_domain.config import get_credential

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.dict(
                os.environ,
                {"CREDENTIALS_DIRECTORY": tmpdir, "MY_CRED": "from_env"},
                clear=False,
            ),
        ):
            result = get_credential("MY_CRED")
            assert result == "from_env"


class TestTokenValidationMode:
    """Tests for TokenValidationMode enum."""

    def test_enum_values(self):
        """Test enum has expected values."""
        from custom_domain.config import TokenValidationMode

        assert TokenValidationMode.JWT_ONLY == "jwt_only"
        assert TokenValidationMode.INTROSPECTION == "introspection"
        assert TokenValidationMode.TOKEN_EXCHANGE == "token_exchange"


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        """Test default settings values."""
        from custom_domain.config import settings

        assert settings.app_name == "Custom Domain Service"
        assert isinstance(settings.docs_enabled, bool)
        assert isinstance(settings.database_echo, bool)
        assert isinstance(settings.log_level, str)

    def test_no_deployment_specific_defaults(self):
        """The OAuth2 issuer has no built-in value and the admin scope is configurable."""
        from custom_domain.config import Settings

        defaults = Settings(_env_file=None)
        assert defaults.oauth2_issuer == ""
        assert defaults.admin_scope == "custom-domain:admin"

    def test_base_dir_property(self):
        """Test base_dir property returns correct path."""
        from custom_domain.config import settings

        base_dir = settings.base_dir
        assert base_dir.exists()
        assert (base_dir / "custom_domain").exists()

    def test_settings_has_required_attributes(self):
        """Test settings has all required attributes."""
        from custom_domain.config import settings

        # Check required attributes exist
        assert hasattr(settings, "database_url")
        assert hasattr(settings, "redis_url")
        assert hasattr(settings, "oauth2_issuer")
        assert hasattr(settings, "nginx_sites_dir")
        assert hasattr(settings, "certbot_enabled")
        assert hasattr(settings, "celery_broker_url")
