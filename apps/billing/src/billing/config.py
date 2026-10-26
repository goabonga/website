# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
