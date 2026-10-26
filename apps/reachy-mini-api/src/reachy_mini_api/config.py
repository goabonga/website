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

    app_name: str = "Reachy Mini API"
    debug: bool = False
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["GET", "POST"]
    cors_headers: list[str] = ["*"]

    # OAuth2 / OIDC configuration
    oauth2_issuer: str = ""  # OIDC issuer URL (e.g., https://auth.example.com)
    oauth2_swagger_client_id: str = ""  # OAuth2 PKCE client ID for Swagger UI

    # OAuth2 confidential client for token introspection (RFC 7662) and exchange (RFC 8693)
    oauth2_client_id: str = ""
    oauth2_client_secret: str = get_credential("OAUTH2_CLIENT_SECRET", "")

    # Redis for the introspection and token exchange cache
    redis_url: str = ""  # e.g., unix:///run/redis/redis.sock?db=5
    redis_key_prefix: str = "reachy"
    oauth2_client_cache_ttl: int = 300  # token exchange cache, 5 minutes

    # Token introspection cache (RFC 7662)
    token_introspection_cache_ttl: int = 60  # seconds

    # Trusted issuers (comma-separated list of additional trusted OIDC issuers)
    oauth2_trusted_issuers: str = ""

    # JWKS cache TTL (seconds)
    jwks_cache_ttl: int = 3600  # 1 hour

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
