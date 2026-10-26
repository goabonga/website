# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
