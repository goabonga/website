# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Custom Domain Service"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_echo: bool = False

    # CORS
    cors_origins: list[str] = []
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database (Unix socket format, converted by database.py)
    database_url: str = "postgresql:///custom_domain"
    database_pool_size: int = 5
    database_max_overflow: int = 10

    @property
    def base_dir(self) -> Path:
        """Get the directory that contains the application package."""
        return Path(__file__).parent.parent


settings = Settings()
