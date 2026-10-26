# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.config module."""

from backend.config import Settings, get_credential


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_application_defaults(self, monkeypatch):
        """Application settings have sensible defaults."""
        for name in ("APP_NAME", "DEBUG", "LOG_LEVEL", "DOCS_ENABLED"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.app_name == "GOABONGA API"
        assert s.debug is False
        assert s.log_level == "INFO"
        assert s.docs_enabled is False

    def test_cors_defaults_are_permissive(self, monkeypatch):
        """CORS defaults allow every origin, method and header."""
        for name in ("CORS_ORIGINS", "CORS_CREDENTIALS", "CORS_METHODS", "CORS_HEADERS"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.cors_origins == ["*"]
        assert s.cors_credentials is True
        assert s.cors_methods == ["*"]
        assert s.cors_headers == ["*"]

    def test_database_url_default(self, monkeypatch):
        """DATABASE_URL defaults to a local PostgreSQL database."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert Settings(_env_file=None).database_url == "postgresql://localhost/app"

    def test_values_come_from_environment(self, monkeypatch):
        """Environment variables override defaults, case-insensitively."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("docs_enabled", "true")
        s = Settings(_env_file=None)
        assert s.log_level == "DEBUG"
        assert s.docs_enabled is True

    def test_oauth2_defaults(self, monkeypatch):
        """OAuth2 is unconfigured by default and caches use short TTLs."""
        for name in (
            "OAUTH2_ISSUER",
            "OAUTH2_SWAGGER_CLIENT_ID",
            "OAUTH2_CLIENT_ID",
            "OAUTH2_CLIENT_SECRET",
            "OAUTH2_TRUSTED_ISSUERS",
            "OAUTH2_CLIENT_CACHE_TTL",
            "TOKEN_INTROSPECTION_CACHE_TTL",
            "JWKS_CACHE_TTL",
            "REDIS_URL",
            "REDIS_KEY_PREFIX",
        ):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.oauth2_issuer == ""
        assert s.oauth2_client_id == ""
        assert s.oauth2_client_secret == ""
        assert s.oauth2_client_cache_ttl == 300
        assert s.token_introspection_cache_ttl == 60
        assert s.jwks_cache_ttl == 3600
        assert s.redis_url == ""
        assert s.redis_key_prefix == "fastapi"

    def test_rate_limit_defaults(self, monkeypatch):
        """Rate limits default to 10 anonymous and 60 authenticated requests per minute."""
        for name in (
            "RATE_LIMIT_REDIS_URL",
            "RATE_LIMIT_ANON",
            "RATE_LIMIT_AUTH",
            "RATE_LIMIT_WINDOW",
            "SESSION_CREATE_LIMIT",
            "SESSION_CREATE_WINDOW",
        ):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.rate_limit_redis_url == "redis://localhost:6379/1"
        assert s.rate_limit_anon == 10
        assert s.rate_limit_auth == 60
        assert s.rate_limit_window == 60
        assert s.session_create_limit == 3
        assert s.session_create_window == 86400

    def test_session_defaults(self, monkeypatch):
        """Session data is cached in Redis for one hour."""
        for name in ("SESSION_REDIS_URL", "SESSION_REDIS_TTL"):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.session_redis_url == "redis://localhost:6379/2"
        assert s.session_redis_ttl == 3600

    def test_conversation_cache_and_celery_defaults(self, monkeypatch):
        """Conversations are cached 30 minutes and synced every 30 seconds."""
        for name in (
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
            "CONVERSATION_CACHE_TTL",
            "CONVERSATION_SYNC_INTERVAL",
        ):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.celery_broker_url == "redis://localhost:6379/0"
        assert s.celery_result_backend == "redis://localhost:6379/0"
        assert s.conversation_cache_ttl == 1800
        assert s.conversation_sync_interval == 30

    def test_openai_and_rag_defaults(self, monkeypatch):
        """Embeddings use text-embedding-3-small with a 0.7 similarity threshold."""
        for name in (
            "OPENAI_API_KEY",
            "RAG_EMBEDDING_MODEL",
            "RAG_SIMILARITY_THRESHOLD",
            "RAG_MAX_RESULTS",
        ):
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=None)
        assert s.openai_api_key == ""
        assert s.rag_embedding_model == "text-embedding-3-small"
        assert s.rag_similarity_threshold == 0.7
        assert s.rag_max_results == 5


class TestGetCredential:
    """Tests for get_credential."""

    def test_from_systemd_credentials_directory(self, tmp_path, monkeypatch):
        """A file in CREDENTIALS_DIRECTORY wins and is stripped."""
        (tmp_path / "MY_SECRET").write_text("  secret-value-from-file  \n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MY_SECRET", "env-value")
        assert get_credential("MY_SECRET", default="fallback") == "secret-value-from-file"

    def test_from_environment_variable(self, monkeypatch):
        """Without a credentials directory the environment variable is used."""
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.setenv("MY_SECRET", "env-value")
        assert get_credential("MY_SECRET", default="fallback") == "env-value"

    def test_returns_default_when_not_found(self, monkeypatch):
        """The default is returned when neither source has the secret."""
        monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        assert get_credential("NONEXISTENT_KEY", default="my-default") == "my-default"

    def test_missing_file_falls_back_to_environment(self, tmp_path, monkeypatch):
        """A set but empty credentials directory falls back to the environment."""
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("MISSING_SECRET", "from-env-var")
        assert get_credential("MISSING_SECRET", default="fallback") == "from-env-var"

    def test_openai_api_key_comes_from_credentials(self, tmp_path, monkeypatch):
        """The OpenAI key is read from the systemd credentials directory first."""
        (tmp_path / "OPENAI_API_KEY").write_text("sk-from-file\n")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        import importlib

        import backend.config

        try:
            reloaded = importlib.reload(backend.config)
            assert reloaded.settings.openai_api_key == "sk-from-file"
        finally:
            monkeypatch.undo()
            importlib.reload(backend.config)
