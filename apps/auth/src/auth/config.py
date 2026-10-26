# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., JWKS_ENCRYPTION_KEY).
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
    """Application settings."""

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # API documentation (Swagger UI at /docs)
    app_title: str = "OIDC/OAuth2 Service"  # Title of the OpenAPI document and of the docs page
    swagger_client_id: str = "swagger-ui"  # client_id the Swagger UI "Authorize" button uses
    swagger_scopes: str = "openid profile email"  # Space-separated scopes it requests

    # Database (supports postgresql://, postgres://, postgresql+asyncpg://)
    database_url: str = "postgresql://localhost:5432/auth"

    # Database pool settings
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env")


# Load settings with credential overrides for secrets
settings = Settings()
