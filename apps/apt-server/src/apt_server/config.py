# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

from functools import lru_cache
from typing import Annotated, Any

from pydantic import AnyUrl, BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    """Parse CORS origins from string or list.

    Accepts:
        - Comma-separated string: "https://a.com, https://b.com"
        - JSON array string: '["https://a.com", "https://b.com"]'
        - Python list: ["https://a.com", "https://b.com"]
    """
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "apt-server"
    log_level: str = "INFO"
    docs_enabled: bool = False

    # CORS
    # Allowed origins for CORS requests.
    # Accepts comma-separated string or JSON array in .env:
    #   BACKEND_CORS_ORIGINS="https://app.example.com,https://admin.example.com"
    #   BACKEND_CORS_ORIGINS='["https://app.example.com"]'
    backend_cors_origins: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []
    # Frontend host appended to CORS origins (e.g. "https://frontend.example.com")
    frontend_host: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """Merge backend_cors_origins and frontend_host into a single list.

        Trailing slashes are stripped to avoid mismatches.
        Used by CORSMiddleware in main.py.
        """
        return [str(origin).rstrip("/") for origin in self.backend_cors_origins] + (
            [self.frontend_host] if self.frontend_host else []
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
