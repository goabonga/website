# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.config module."""

import os
from pathlib import Path
from unittest.mock import patch

from mailler.config import Settings, get_credential


class TestSettingsDefaults:
    """Default values of the application settings."""

    def test_application_defaults(self):
        s = Settings(_env_file=None)
        assert s.app_name == "Mailler API"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False
        assert s.database_echo is False

    def test_database_default(self):
        assert Settings(_env_file=None).database_url == "postgresql:///mailler"

    def test_cors_defaults(self):
        s = Settings(_env_file=None)
        assert s.cors_origins == []
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]


class TestSettingsFromEnvironment:
    """Settings are read from environment variables."""

    def test_environment_overrides_default(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DOCS_ENABLED", "true")
        monkeypatch.setenv("CORS_ORIGINS", '["https://example.test"]')
        s = Settings(_env_file=None)
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://example.test"]

    def test_unknown_variables_are_ignored(self, monkeypatch):
        monkeypatch.setenv("SOMETHING_UNKNOWN", "x")
        assert not hasattr(Settings(_env_file=None), "something_unknown")


class TestAuthSettings:
    """OAuth2 and cache settings introduced with authentication."""

    def test_oauth2_defaults(self):
        s = Settings(_env_file=None)
        assert s.oauth2_issuer == ""
        assert s.admin_scope == "mailler:admin"
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""
        assert s.oauth2_swagger_client_id == ""
        assert s.oauth2_trusted_issuers == ""
        assert s.oauth2_client_cache_ttl == 300
        assert s.token_introspection_cache_ttl == 60
        assert s.jwks_cache_ttl == 3600

    def test_redis_defaults(self):
        s = Settings(_env_file=None)
        assert s.redis_url == "redis://localhost:6379/11"
        assert s.redis_key_prefix == "mailler"


class TestGetCredential:
    """Tests for get_credential function."""

    def test_reads_from_credentials_directory(self, tmp_path: Path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("secret-value\n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}):
            result = get_credential("MY_SECRET", "default")

        assert result == "secret-value"

    def test_strips_whitespace_from_credential_file(self, tmp_path: Path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  secret  \n")

        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}):
            result = get_credential("MY_SECRET")

        assert result == "secret"

    def test_falls_back_to_env_var(self):
        with patch.dict(
            os.environ,
            {"MY_SECRET": "env-value"},
            clear=False,
        ):
            # Remove CREDENTIALS_DIRECTORY if set
            env = dict(os.environ)
            env.pop("CREDENTIALS_DIRECTORY", None)
            env["MY_SECRET"] = "env-value"
            with patch.dict(os.environ, env, clear=True):
                result = get_credential("MY_SECRET", "default")

        assert result == "env-value"

    def test_returns_default_when_not_found(self):
        with patch.dict(os.environ, {}, clear=True):
            result = get_credential("NONEXISTENT", "default-val")

        assert result == "default-val"

    def test_returns_empty_string_default(self):
        with patch.dict(os.environ, {}, clear=True):
            result = get_credential("NONEXISTENT")

        assert result == ""

    def test_credential_file_takes_priority_over_env(self, tmp_path: Path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("file-value")

        with patch.dict(
            os.environ,
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MY_SECRET": "env-value"},
        ):
            result = get_credential("MY_SECRET", "default")

        assert result == "file-value"

    def test_missing_credential_file_falls_back_to_env(self, tmp_path: Path):
        with patch.dict(
            os.environ,
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MY_SECRET": "env-value"},
        ):
            result = get_credential("MY_SECRET", "default")

        assert result == "env-value"


class TestProviderSettings:
    """Sender and provider settings introduced with the providers."""

    def test_defaults(self):
        s = Settings(_env_file=None)
        assert s.default_from == ""
        assert s.default_from_name == ""
        assert s.brevo_api_key == ""
        assert s.sendgrid_api_key == ""
        assert s.ses_region == ""
        assert s.protonmail_host == ""
        assert s.protonmail_port == 0
        assert s.webhook_hmac_secret == ""
        assert s.unsubscribe_base_url == ""

    def test_provider_secrets_read_from_credentials_directory(self, tmp_path):
        (tmp_path / "BREVO_API_KEY").write_text("brevo-secret\n")
        (tmp_path / "WEBHOOK_HMAC_SECRET").write_text("hmac-secret\n")
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(tmp_path)}):
            import importlib

            import mailler.config as config_module

            reloaded = importlib.reload(config_module)
            try:
                assert reloaded.settings.brevo_api_key == "brevo-secret"
                assert reloaded.settings.webhook_hmac_secret == "hmac-secret"
            finally:
                importlib.reload(config_module)


class TestCelerySettings:
    """Celery broker settings introduced with sending."""

    def test_defaults(self):
        s = Settings(_env_file=None)
        assert s.celery_broker_url == "redis://localhost:6379/0"
        assert s.celery_result_backend == "redis://localhost:6379/1"
        assert s.celery_queue == "mailler"

    def test_delivery_retry_defaults(self):
        s = Settings(_env_file=None)
        assert s.send_max_retries == 3
        assert s.send_retry_delay == 60
        assert s.send_retry_backoff_max == 300

    def test_queue_and_retries_from_environment(self, monkeypatch):
        monkeypatch.setenv("CELERY_QUEUE", "outgoing")
        monkeypatch.setenv("SEND_MAX_RETRIES", "5")
        s = Settings(_env_file=None)
        assert s.celery_queue == "outgoing"
        assert s.send_max_retries == 5
