# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "GOABONGA"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = False
    static_dir: str = ""  # Vite build output; defaults to <app>/web/dist

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Frontend config injection
    auth_url: str = ""
    api_url: str = ""
    analytics_url: str = ""  # Analytics service URL, injected in the page
    oauth2_client_id: str = ""  # Public PKCE client for frontend authentication

    # Legal/Policies information
    legal_company_name: str = "GOABONGA"
    legal_address: str = ""
    legal_city: str = ""
    legal_country: str = ""
    legal_director_name: str = ""
    legal_host_name: str = ""
    legal_host_address: str = ""
    legal_host_city: str = ""
    legal_host_country: str = ""
    legal_host_phone: str = ""
    legal_host_website: str = ""

    # Welcome page
    welcome_name: str = "Chris"
    welcome_words: str = "super,cool,awesome,great"

    # Social links
    social_linkedin: str = ""
    social_github: str = ""
    social_huggingface: str = ""


settings = Settings()
