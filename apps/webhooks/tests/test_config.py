# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for webhooks.config module."""

from unittest.mock import MagicMock, patch

from webhooks.config import Settings, get_credential


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "Webhooks"
        assert s.log_level == "INFO"
        assert s.docs_enabled is False
        assert s.cors_origins == []
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]
        assert s.oauth2_token_url == ""
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""

    def test_env_override(self):
        env = {
            "APP_NAME": "custom-webhooks",
            "LOG_LEVEL": "DEBUG",
            "DOCS_ENABLED": "true",
            "CORS_ORIGINS": '["https://a.example","https://b.example"]',
            "CORS_CREDENTIALS": "false",
            "CORS_METHODS": '["GET","POST"]',
            "CORS_HEADERS": '["X-Test"]',
            "OAUTH2_TOKEN_URL": "https://auth.example.com/token",
            "OAUTH2_CLIENT_ID": "webhooks",
            "OAUTH2_CLIENT_SECRET": "oauth-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "custom-webhooks"
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True
        assert s.cors_origins == ["https://a.example", "https://b.example"]
        assert s.cors_credentials is False
        assert s.cors_methods == ["GET", "POST"]
        assert s.cors_headers == ["X-Test"]
        assert s.oauth2_token_url == "https://auth.example.com/token"
        assert s.oauth2_client_id == "webhooks"
        assert s.oauth2_client_secret == "oauth-secret"

    def test_env_names_are_case_insensitive(self):
        with patch.dict("os.environ", {"app_name": "lower"}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_name == "lower"


class TestGetCredential:
    """Tests for get_credential function."""

    def test_reads_from_credentials_directory(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "  file-secret  \n"

        with (
            patch.dict("os.environ", {"CREDENTIALS_DIRECTORY": "/run/creds"}, clear=True),
            patch("webhooks.config.Path") as mock_path_cls,
        ):
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_path)
            result = get_credential("MY_SECRET", "default-val")

        assert result == "file-secret"
        mock_path.read_text.assert_called_once()

    def test_falls_back_to_env_var(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with (
            patch.dict(
                "os.environ",
                {"CREDENTIALS_DIRECTORY": "/run/creds", "MY_SECRET": "env-secret"},
                clear=True,
            ),
            patch("webhooks.config.Path") as mock_path_cls,
        ):
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_path)
            result = get_credential("MY_SECRET", "default-val")

        assert result == "env-secret"

    def test_falls_back_to_default(self):
        with patch.dict("os.environ", {}, clear=True):
            result = get_credential("MY_SECRET", "default-val")
        assert result == "default-val"

    def test_falls_back_to_empty_string_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            result = get_credential("MY_SECRET")
        assert result == ""

    def test_no_credentials_directory_uses_env_var(self):
        with patch.dict("os.environ", {"MY_SECRET": "from-env"}, clear=True):
            result = get_credential("MY_SECRET", "default")
        assert result == "from-env"

    def test_credential_file_content_is_stripped(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "\n  secret-with-whitespace  \n\n"

        with (
            patch.dict("os.environ", {"CREDENTIALS_DIRECTORY": "/run/creds"}, clear=True),
            patch("webhooks.config.Path") as mock_path_cls,
        ):
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_path)
            result = get_credential("MY_SECRET")

        assert result == "secret-with-whitespace"


class TestModuleSettings:
    """Tests for the module-level settings object."""

    def test_oauth2_secret_loaded_from_credentials_directory(self, tmp_path):
        import importlib

        import webhooks.config as config_module

        (tmp_path / "OAUTH2_CLIENT_SECRET").write_text("from-credential\n")
        env = {"CREDENTIALS_DIRECTORY": str(tmp_path)}
        try:
            with patch.dict("os.environ", env, clear=True):
                reloaded = importlib.reload(config_module)
                assert reloaded.settings.oauth2_client_secret == "from-credential"
        finally:
            importlib.reload(config_module)


class TestBrevoSettings:
    """Tests for the Brevo settings."""

    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.brevo_enabled is False
        assert s.brevo_webhook_secret == ""
        assert s.brevo_internal_api_url == ""
        assert s.brevo_internal_api_socket == ""
        assert s.brevo_internal_api_token == ""

    def test_env_override(self):
        env = {
            "BREVO_ENABLED": "true",
            "BREVO_INTERNAL_API_URL": "http://brevo-api:8000",
            "BREVO_INTERNAL_API_SOCKET": "/run/brevo-internal.sock",
            "BREVO_INTERNAL_API_TOKEN": "brevo-token",
            "BREVO_WEBHOOK_SECRET": "brevo-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.brevo_enabled is True
        assert s.brevo_internal_api_url == "http://brevo-api:8000"
        assert s.brevo_internal_api_socket == "/run/brevo-internal.sock"
        assert s.brevo_internal_api_token == "brevo-token"
        assert s.brevo_webhook_secret == "brevo-secret"


class TestSESSettings:
    """Tests for the SES settings."""

    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
        assert s.ses_enabled is False
        assert s.ses_internal_api_url == ""
        assert s.ses_internal_api_socket == ""
        assert s.ses_internal_api_token == ""

    def test_env_override(self):
        env = {
            "SES_ENABLED": "true",
            "SES_INTERNAL_API_URL": "http://ses-api:8000",
            "SES_INTERNAL_API_SOCKET": "/run/ses-internal.sock",
            "SES_INTERNAL_API_TOKEN": "ses-token",
        }
        with patch.dict("os.environ", env, clear=True):
            s = Settings(_env_file=None)
        assert s.ses_enabled is True
        assert s.ses_internal_api_url == "http://ses-api:8000"
        assert s.ses_internal_api_socket == "/run/ses-internal.sock"
        assert s.ses_internal_api_token == "ses-token"
