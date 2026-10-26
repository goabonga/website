# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Configuration settings for Mailler API."""

import os
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


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Mailler API"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_echo: bool = False

    # CORS
    cors_origins: list[str] = []  # no origin is allowed until configured
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql:///mailler"

    # Redis
    redis_url: str = "redis://localhost:6379/11"
    redis_key_prefix: str = "mailler"  # Cache key prefix for auth tokens

    # OAuth2 / OIDC
    oauth2_issuer: str = ""  # empty disables authentication (503)
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_swagger_client_id: str = ""
    admin_scope: str = "mailler:admin"  # scope allowing a caller to cross the client boundary
    oauth2_trusted_issuers: str = ""  # Comma-separated additional trusted issuers
    oauth2_client_cache_ttl: int = 300
    token_introspection_cache_ttl: int = 60
    jwks_cache_ttl: int = 3600  # 1 hour


# Load settings with credential support
settings = Settings(
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET", os.environ.get("OAUTH2_CLIENT_SECRET", "")
    ),
)
