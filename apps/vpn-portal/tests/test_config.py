# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal.config."""

import pytest
from vpn_portal.config import Settings, get_credential

MANAGED = (
    "APP_NAME",
    "DEBUG",
    "DOCS_ENABLED",
    "LOG_LEVEL",
    "OAUTH2_ISSUER",
    "OAUTH2_SWAGGER_CLIENT_ID",
    "OAUTH2_CLIENT_ID",
    "OAUTH2_CLIENT_SECRET",
    "OAUTH2_CLIENT_CACHE_TTL",
    "OAUTH2_TRUSTED_ISSUERS",
    "TOKEN_INTROSPECTION_CACHE_TTL",
    "JWKS_CACHE_TTL",
    "REDIS_URL",
    "REDIS_KEY_PREFIX",
    "CREDENTIALS_DIRECTORY",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in MANAGED:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    settings = Settings(_env_file=None)

    assert settings.app_name == "VPN Portal"
    assert settings.debug is False
    assert settings.docs_enabled is True
    assert settings.log_level == "INFO"


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Portal")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "Portal"
    assert settings.debug is True
    assert settings.docs_enabled is False
    assert settings.log_level == "DEBUG"


def test_env_file_is_read(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=From File\nLOG_LEVEL=WARNING\n")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "From File"
    assert settings.log_level == "WARNING"


def test_environment_wins_over_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    assert Settings(_env_file=env_file).log_level == "ERROR"


def test_oauth2_defaults():
    settings = Settings(_env_file=None)

    assert settings.oauth2_issuer == ""
    assert settings.oauth2_swagger_client_id == ""
    assert settings.oauth2_client_id == ""
    assert settings.oauth2_client_secret == ""
    assert settings.oauth2_trusted_issuers == ""
    assert settings.redis_url == ""
    assert settings.redis_key_prefix == "vpn"
    assert settings.oauth2_client_cache_ttl == 300
    assert settings.token_introspection_cache_ttl == 60
    assert settings.jwks_cache_ttl == 3600


def test_oauth2_environment_overrides(monkeypatch):
    monkeypatch.setenv("OAUTH2_ISSUER", "https://auth.example.com")
    monkeypatch.setenv("OAUTH2_CLIENT_ID", "portal")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/8")
    monkeypatch.setenv("OAUTH2_CLIENT_CACHE_TTL", "10")
    monkeypatch.setenv("TOKEN_INTROSPECTION_CACHE_TTL", "5")
    monkeypatch.setenv("JWKS_CACHE_TTL", "7")

    settings = Settings(_env_file=None)

    assert settings.oauth2_issuer == "https://auth.example.com"
    assert settings.oauth2_client_id == "portal"
    assert settings.redis_url == "redis://localhost:6379/8"
    assert settings.oauth2_client_cache_ttl == 10
    assert settings.token_introspection_cache_ttl == 5
    assert settings.jwks_cache_ttl == 7


class TestGetCredential:
    def test_returns_default_when_nothing_is_set(self):
        assert get_credential("MY_SECRET", "fallback") == "fallback"

    def test_default_is_empty_string(self):
        assert get_credential("MY_SECRET") == ""

    def test_reads_environment_variable(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "from-env")

        assert get_credential("MY_SECRET", "default") == "from-env"

    def test_reads_systemd_credential(self, tmp_path, monkeypatch):
        (tmp_path / "MY_SECRET").write_text("  from-systemd  \n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))

        assert get_credential("MY_SECRET", "default") == "from-systemd"

    def test_systemd_credential_wins_over_environment(self, tmp_path, monkeypatch):
        (tmp_path / "MY_SECRET").write_text("from-systemd")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MY_SECRET", "from-env")

        assert get_credential("MY_SECRET") == "from-systemd"

    def test_missing_credential_file_falls_back_to_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MY_SECRET", "from-env")

        assert get_credential("MY_SECRET") == "from-env"
