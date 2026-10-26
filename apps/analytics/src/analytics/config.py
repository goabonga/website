# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., SECRET_KEY).
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
    app_name: str = "Analytics"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_echo: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["GET", "POST", "OPTIONS"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql://localhost:5432/analytics"

    # Redis
    redis_url: str = "redis://localhost:6379/7"
    cache_ttl: int = 300  # 5 minutes

    # GeoIP configuration
    geoip_enabled: bool = True
    geoip_database_path: str = "/usr/share/GeoIP/GeoLite2-City.mmdb"

    # Tracking configuration
    session_cookie_name: str = "ua_sid"
    session_cookie_max_age: int = 86400 * 365  # 1 year
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "none"
    session_cookie_domain: str = ""

    # Pixel configuration
    pixel_cache_control: str = "no-cache, no-store, must-revalidate"

    # Data retention (GDPR compliance)
    data_retention_days: int = 395  # ~13 months

    # IP anonymization (GDPR compliance)
    anonymize_ip: bool = False  # Set to True to mask last octet

    # OAuth2 / OIDC configuration
    oauth2_issuer: str = ""  # OIDC issuer URL (e.g., https://auth.example.com)
    oauth2_swagger_client_id: str = ""  # Public PKCE client for Swagger UI
    oauth2_client_id: str = ""  # Confidential client for introspection
    oauth2_client_secret: str = ""  # Client secret for introspection

    # Token introspection cache (RFC 7662)
    token_introspection_cache_ttl: int = 60  # seconds

    # Token exchange cache (RFC 8693)
    oauth2_client_cache_ttl: int = 300  # Cache exchanged scopes (seconds)

    # security.txt (RFC 9116)
    security_contact: str = ""
    security_expires: str = ""
    security_encryption: str = ""
    security_acknowledgments: str = ""
    security_preferred_languages: str = ""
    security_canonical: str = ""
    security_policy: str = ""
    security_hiring: str = ""
    security_csaf: str = ""


# Load settings with credential overrides for secrets
@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings(
        oauth2_client_secret=get_credential(
            "OAUTH2_CLIENT_SECRET",
            os.environ.get("OAUTH2_CLIENT_SECRET", ""),
        ),
    )


settings = get_settings()
