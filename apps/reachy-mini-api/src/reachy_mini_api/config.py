# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Trusted issuers (comma-separated list of additional trusted OIDC issuers)
    oauth2_trusted_issuers: str = ""

    # JWKS cache TTL (seconds)
    jwks_cache_ttl: int = 3600  # 1 hour

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
