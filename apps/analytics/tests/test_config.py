# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.config module."""

from unittest.mock import patch

from analytics.config import Settings, get_credential


class TestGetCredential:
    """Tests for get_credential function."""

    def test_returns_default_when_no_env(self):
        with patch.dict("os.environ", {}, clear=True):
            result = get_credential("TEST_SECRET", "default_value")
        assert result == "default_value"

    def test_returns_env_variable(self):
        with patch.dict("os.environ", {"MY_SECRET": "env_value"}, clear=True):
            result = get_credential("MY_SECRET", "default")
        assert result == "env_value"

    def test_reads_from_credentials_directory(self, tmp_path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("  credential_value  ")

        with patch.dict("os.environ", {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=True):
            result = get_credential("MY_SECRET", "default")
        assert result == "credential_value"

    def test_credentials_directory_takes_priority(self, tmp_path):
        cred_file = tmp_path / "MY_SECRET"
        cred_file.write_text("cred_value")

        with patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MY_SECRET": "env_value"},
            clear=True,
        ):
            result = get_credential("MY_SECRET", "default")
        assert result == "cred_value"

    def test_falls_back_to_env_when_cred_file_missing(self, tmp_path):
        with patch.dict(
            "os.environ",
            {"CREDENTIALS_DIRECTORY": str(tmp_path), "MY_SECRET": "env_value"},
            clear=True,
        ):
            result = get_credential("MY_SECRET", "default")
        assert result == "env_value"

    def test_empty_default(self):
        with patch.dict("os.environ", {}, clear=True):
            result = get_credential("NONEXISTENT")
        assert result == ""


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Analytics"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False

    def test_cors_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.cors_origins == ["*"]
        assert s.cors_credentials is True
        assert s.cors_methods == ["GET", "POST", "OPTIONS"]
        assert s.cors_headers == ["*"]

    def test_env_override(self):
        env = {
            "APP_NAME": "CustomApp",
            "LOG_LEVEL": "DEBUG",
            "DOCS_ENABLED": "true",
            "CORS_ORIGINS": '["https://example.com"]',
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "CustomApp"
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://example.com"]

    def test_env_is_case_insensitive(self):
        with patch.dict("os.environ", {"app_name": "lower"}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "lower"

    def test_security_txt_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.security_contact == ""
        assert s.security_expires == ""
        assert s.security_encryption == ""
        assert s.security_csaf == ""

    def test_security_txt_env_override(self):
        env = {
            "SECURITY_CONTACT": "mailto:security@example.com",
            "SECURITY_POLICY": "https://example.com/policy",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.security_contact == "mailto:security@example.com"
        assert s.security_policy == "https://example.com/policy"

    def test_database_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.database_url == "postgresql://localhost:5432/analytics"
        assert s.database_echo is False
        assert s.data_retention_days == 395

    def test_database_env_override(self):
        env = {
            "DATABASE_URL": "postgresql:///analytics",
            "DATABASE_ECHO": "true",
            "DATA_RETENTION_DAYS": "30",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.database_url == "postgresql:///analytics"
        assert s.database_echo is True
        assert s.data_retention_days == 30

    def test_geoip_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.geoip_enabled is True
        assert s.geoip_database_path == "/usr/share/GeoIP/GeoLite2-City.mmdb"

    def test_geoip_env_override(self):
        env = {"GEOIP_ENABLED": "false", "GEOIP_DATABASE_PATH": "/tmp/city.mmdb"}
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.geoip_enabled is False
        assert s.geoip_database_path == "/tmp/city.mmdb"

    def test_session_cookie_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.session_cookie_name == "ua_sid"
        assert s.session_cookie_max_age == 86400 * 365
        assert s.session_cookie_secure is True
        assert s.session_cookie_samesite == "none"
        assert s.session_cookie_domain == ""

    def test_pixel_and_privacy_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.pixel_cache_control == "no-cache, no-store, must-revalidate"
        assert s.anonymize_ip is False

    def test_anonymize_ip_env_override(self):
        with patch.dict("os.environ", {"ANONYMIZE_IP": "true"}, clear=True):
            s = Settings(_env_file=None)
        assert s.anonymize_ip is True

    def test_oauth2_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.oauth2_issuer == ""
        assert s.oauth2_swagger_client_id == ""
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""
        assert s.token_introspection_cache_ttl == 60
        assert s.oauth2_client_cache_ttl == 300

    def test_redis_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.redis_url == "redis://localhost:6379/7"
        assert s.cache_ttl == 300

    def test_oauth2_client_secret_comes_from_credential(self, tmp_path):
        from analytics.config import get_settings

        (tmp_path / "OAUTH2_CLIENT_SECRET").write_text("from-credential\n")
        get_settings.cache_clear()
        try:
            with patch.dict("os.environ", {"CREDENTIALS_DIRECTORY": str(tmp_path)}, clear=True):
                s = get_settings()
            assert s.oauth2_client_secret == "from-credential"
        finally:
            get_settings.cache_clear()
