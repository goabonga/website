# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., OAUTH2_CLIENT_SECRET).
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
    """Application settings, read from the environment and an optional ``.env`` file."""

    # Application
    app_name: str = "VPN Portal"
    debug: bool = False
    docs_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    # OAuth2 / OIDC configuration
    oauth2_issuer: str = ""  # OIDC issuer URL (e.g., https://auth.example.com)
    oauth2_swagger_client_id: str = ""  # OAuth2 PKCE client ID for Swagger UI

    # OAuth2 confidential client for token exchange (RFC 8693)
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Redis for token exchange and introspection cache
    redis_url: str = ""  # e.g., unix:///run/redis/redis.sock?db=8
    redis_key_prefix: str = "vpn"  # Cache key prefix for auth tokens
    oauth2_client_cache_ttl: int = 300  # 5 minutes

    # Token introspection cache (RFC 7662)
    token_introspection_cache_ttl: int = 60  # seconds

    # JWKS cache TTL (seconds)
    jwks_cache_ttl: int = 3600  # 1 hour

    # Trusted issuers (comma-separated, in addition to oauth2_issuer)
    oauth2_trusted_issuers: str = ""

    model_config = SettingsConfigDict(env_file=".env")


# Load settings with credential overrides for secrets
settings = Settings(
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET",
        os.environ.get("OAUTH2_CLIENT_SECRET", ""),
    ),
)
