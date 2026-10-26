# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration using Pydantic Settings."""

import os
from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read credential from systemd credentials directory or environment.

    Args:
        name: Credential name
        default: Default value if not found

    Returns:
        Credential value
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


class TokenValidationMode(StrEnum):
    """Token validation modes."""

    JWT_ONLY = "jwt_only"
    INTROSPECTION = "introspection"
    TOKEN_EXCHANGE = "token_exchange"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Custom Domain Service"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_echo: bool = False

    # CORS
    cors_origins: list[str] = []
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database (Unix socket format, converted by database.py)
    database_url: str = "postgresql:///custom_domain"
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/13"
    redis_key_prefix: str = "custom-domain"

    # OAuth2 / OIDC
    oauth2_issuer: str = ""
    admin_scope: str = "custom-domain:admin"
    oauth2_swagger_client_id: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_trusted_issuers: str = ""
    oauth2_client_cache_ttl: int = 300
    oauth2_http_timeout_seconds: float = 10.0
    token_introspection_cache_ttl: int = 60
    token_validation_mode: TokenValidationMode = TokenValidationMode.INTROSPECTION
    token_exchange_cache_ttl: int = 300
    jwks_cache_ttl: int = 3600
    oauth2_introspection_endpoint: str | None = None
    oauth2_token_endpoint: str | None = None
    oauth2_jwks_uri: str | None = None

    @property
    def base_dir(self) -> Path:
        """Get the directory that contains the application package."""
        return Path(__file__).parent.parent


# Load settings with credential support
settings = Settings(
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET", os.environ.get("OAUTH2_CLIENT_SECRET", "")
    ),
)
