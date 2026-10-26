# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., OPENAI_API_KEY).
        default: Default value if not found.

    Returns:
        The credential value.
    """
    # First check systemd credentials directory
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()

    # Fall back to environment variable
    return os.environ.get(name, default)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Team"
    docs_enabled: bool = True
    database_echo: bool = False
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql+asyncpg://team:team@localhost:5432/team"

    # Redis
    redis_url: str = "redis://localhost:6379/10"
    redis_key_prefix: str = "team"

    # OAuth2 / OIDC
    oauth2_issuer: str = ""
    oauth2_swagger_client_id: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_trusted_issuers: str = ""
    oauth2_token_cache_ttl: int = 300
    oauth2_introspection_cache_ttl: int = 60
    token_introspection_cache_ttl: int = 60
    oauth2_client_cache_ttl: int = 300
    jwks_cache_ttl: int = 3600

    # LLM API keys
    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings(
        openai_api_key=get_credential(
            "OPENAI_API_KEY",
            os.environ.get("OPENAI_API_KEY", ""),
        ),
        oauth2_client_secret=get_credential(
            "OAUTH2_CLIENT_SECRET",
            os.environ.get("OAUTH2_CLIENT_SECRET", ""),
        ),
    )


settings = get_settings()
