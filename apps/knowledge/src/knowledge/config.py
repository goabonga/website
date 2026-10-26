# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Systemd credentials are stored in $CREDENTIALS_DIRECTORY when the service
    is started with LoadCredentialEncrypted. Falls back to environment variables
    for local development.
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Knowledge API"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql+asyncpg://knowledge:knowledge@localhost:5440/knowledge_test"

    # Redis
    redis_url: str = "redis://localhost:6387/0"
    redis_key_prefix: str = "knowledge"

    # OAuth2/OIDC (via auth service)
    oauth2_issuer: str = ""  # e.g., https://auth.example.com

    # Public client (Swagger UI) - uses PKCE, no secret
    oauth2_swagger_client_id: str = ""

    # Confidential client (API server) - for token exchange & introspection
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Token caching
    oauth2_token_cache_ttl: int = 300  # 5 minutes for token exchange
    oauth2_introspection_cache_ttl: int = 60  # 1 minute for introspection
    oauth2_trusted_issuers: str = ""
    jwks_cache_ttl: int = 3600


# Secrets that can be delivered as systemd credentials or environment variables.
CREDENTIAL_FIELDS = {
    "oauth2_client_secret": "OAUTH2_CLIENT_SECRET",
}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance with credential overrides for secrets.

    A secret only overrides the setting when a credential or an environment variable
    provides it, so that a value from the `.env` file stays in effect otherwise.
    """
    settings = Settings()
    for field, name in CREDENTIAL_FIELDS.items():
        value = get_credential(name)
        if value:
            setattr(settings, field, value)
    return settings
