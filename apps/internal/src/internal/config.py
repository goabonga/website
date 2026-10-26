# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_name: str = "GOABONGA API"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Session signing key (read from systemd credentials in production)
    secret_key: str = "change-me-in-production"


# Load settings with credential overrides for secrets
settings = Settings(
    secret_key=get_credential(
        "SECRET_KEY", os.environ.get("SECRET_KEY", "change-me-in-production")
    ),
)
