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
        name: Credential name (e.g., STRIPE_SECRET_KEY).
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
    app_name: str = "Billing API"
    docs_enabled: bool = False
    database_echo: bool = False
    log_level: str = "INFO"

    # CORS
    cors_origins: list[str] = []  # Empty: no cross-origin access
    cors_credentials: bool = False
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql+asyncpg://billing:billing@localhost:5432/billing"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Catalog
    default_currency: str = "usd"  # ISO 4217 code used when a price does not give one
    max_trial_period_days: int = 730  # Upper bound of a trial period given by a caller
    checkout_max_quantity: int = 1000  # Upper bound of the quantity of a checkout line item
    usage_batch_max_events: int = 100  # Largest batch of usage events accepted in one call
    list_default_limit: int = 100  # Page size of the list endpoints
    list_max_limit: int = 1000  # Largest page size a caller can ask for
    # Refuse checkout and portal redirect URLs when the SaaS app lists no allowed prefix
    redirect_allowlist_required: bool = True

    # Redis
    redis_url: str = "redis://localhost:6379/10"
    redis_key_prefix: str = "billing"  # Cache key prefix for auth tokens

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    default_recurring_interval: str = "month"  # Interval of a recurring price that gives none

    # OAuth2/OIDC (via auth service)
    oauth2_issuer: str = ""  # e.g., https://auth.example.invalid
    oauth2_trusted_issuers: str = ""  # Comma-separated additional trusted issuers

    # Public client (Swagger UI) - uses PKCE, no secret
    oauth2_swagger_client_id: str = ""

    # Confidential client (API server) - for token exchange & introspection
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Token caching
    token_introspection_cache_ttl: int = 60  # Alias for introspection cache TTL
    oauth2_client_cache_ttl: int = 300  # Cache TTL for OAuth2 client metadata
    jwks_cache_ttl: int = 3600  # 1 hour
    oauth2_http_timeout: float = 10.0  # seconds, calls to the auth service


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings(
        stripe_secret_key=get_credential(
            "STRIPE_SECRET_KEY",
            os.environ.get("STRIPE_SECRET_KEY", ""),
        ),
        stripe_webhook_secret=get_credential(
            "STRIPE_WEBHOOK_SECRET",
            os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        ),
        oauth2_client_secret=get_credential(
            "OAUTH2_CLIENT_SECRET",
            os.environ.get("OAUTH2_CLIENT_SECRET", ""),
        ),
    )


settings = get_settings()
