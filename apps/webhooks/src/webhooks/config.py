# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., SECRET_KEY).
        default: Default value if not found.

    Returns:
        The credential value.
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
    app_name: str = "Webhooks"
    log_level: str = "INFO"
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = []
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # OAuth2 client credentials (machine-to-machine auth with downstream services)
    oauth2_token_url: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Brevo (Sendinblue) -> Internal API
    brevo_enabled: bool = False
    brevo_webhook_secret: str = ""
    brevo_internal_api_url: str = ""
    brevo_internal_api_socket: str = ""  # Unix socket (overrides URL)
    brevo_internal_api_token: str = ""  # Bearer token for internal API


settings = Settings(
    brevo_webhook_secret=get_credential(
        "BREVO_WEBHOOK_SECRET",
        os.environ.get("BREVO_WEBHOOK_SECRET", ""),
    ),
    brevo_internal_api_token=get_credential(
        "BREVO_INTERNAL_API_TOKEN",
        os.environ.get("BREVO_INTERNAL_API_TOKEN", ""),
    ),
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET",
        os.environ.get("OAUTH2_CLIENT_SECRET", ""),
    ),
)
