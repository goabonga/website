# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.config — get_credential and Settings."""

import os
from unittest.mock import patch

from auth.config import get_credential

# ── get_credential ──────────────────────────────────────────────────────────


class TestGetCredential:
    def test_from_credentials_directory(self, tmp_path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  secret_value  \n")
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}):
            result = get_credential("MY_SECRET", "default")
        assert result == "secret_value"

    def test_creds_dir_file_missing_falls_to_env(self, tmp_path):
        # CREDENTIALS_DIRECTORY exists but file is not there
        with patch.dict(
            os.environ,
            {
                "CREDENTIALS_DIRECTORY": str(tmp_path),
                "MY_SECRET": "from_env",
            },
        ):
            result = get_credential("MY_SECRET", "default")
        assert result == "from_env"

    def test_no_creds_dir_uses_env(self):
        with patch.dict(os.environ, {"MY_SECRET": "env_val"}, clear=False):
            # Make sure CREDENTIALS_DIRECTORY is not set
            env = os.environ.copy()
            env.pop("CREDENTIALS_DIRECTORY", None)
            env["MY_SECRET"] = "env_val"
            with patch.dict(os.environ, env, clear=True):
                result = get_credential("MY_SECRET", "default")
        assert result == "env_val"

    def test_no_creds_dir_no_env_uses_default(self):
        env = os.environ.copy()
        env.pop("CREDENTIALS_DIRECTORY", None)
        env.pop("MISSING_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            result = get_credential("MISSING_KEY", "fallback")
        assert result == "fallback"

    def test_default_empty_string(self):
        env = os.environ.copy()
        env.pop("CREDENTIALS_DIRECTORY", None)
        env.pop("NOPE", None)
        with patch.dict(os.environ, env, clear=True):
            result = get_credential("NOPE")
        assert result == ""


class TestApiDocumentationSettings:
    """The title and the Swagger UI client are settings, with neutral defaults."""

    def test_defaults_carry_no_deployment_value(self):
        from auth.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            configured = Settings(_env_file=None)
        assert configured.app_title == "OIDC/OAuth2 Service"
        assert configured.swagger_client_id == "swagger-ui"
        assert configured.swagger_scopes == "openid profile email"

    def test_environment_overrides_them(self):
        from auth.config import Settings

        env = {
            "APP_TITLE": "Example Auth",
            "SWAGGER_CLIENT_ID": "docs-client",
            "SWAGGER_SCOPES": "openid *",
        }
        with patch.dict(os.environ, env, clear=True):
            configured = Settings(_env_file=None)
        assert configured.app_title == "Example Auth"
        assert configured.swagger_client_id == "docs-client"
        assert configured.swagger_scopes == "openid *"


class TestScopeGroupsSetting:
    def test_empty_by_default(self):
        from auth.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            assert Settings(_env_file=None).scope_groups == {}

    def test_read_from_json(self):
        from auth.config import Settings

        env = {"SCOPE_GROUPS": '{"suite:*": ["notes", "tasks"]}'}
        with patch.dict(os.environ, env, clear=True):
            configured = Settings(_env_file=None)
        assert configured.scope_groups == {"suite:*": ["notes", "tasks"]}
