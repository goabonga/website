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

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "internal"

    # Session signing key (read from systemd credentials in production)
    secret_key: str = "change-me-in-production"

    # Analytics API
    analytics_api_url: str = "https://ua.goabonga.com"

    # Web UI
    app_base_url: str = "https://admin.internal"  # Application URL (for OAuth2 redirect URI)
    cookie_secure: bool = True  # Set to False for local development without HTTPS

    # OAuth2 / OIDC
    oauth2_issuer: str = ""  # OIDC issuer URL (e.g., https://auth.goabonga.com)
    oauth2_swagger_client_id: str = ""  # Public PKCE client for Swagger UI
    oauth2_frontend_client_id: str = ""  # Public PKCE client for HTML pages
    oauth2_client_id: str = ""  # Confidential client for introspection/token exchange
    oauth2_client_secret: str = ""  # Client secret for introspection/token exchange
    oauth2_client_cache_ttl: int = 300  # Cache exchanged tokens for 5 minutes
    token_introspection_cache_ttl: int = 60  # seconds


# Load settings with credential overrides for secrets
settings = Settings(
    secret_key=get_credential(
        "SECRET_KEY", os.environ.get("SECRET_KEY", "change-me-in-production")
    ),
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET", os.environ.get("OAUTH2_CLIENT_SECRET", "")
    ),
)
