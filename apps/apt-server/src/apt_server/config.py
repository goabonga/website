# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from functools import lru_cache
from pathlib import Path
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

    app_name: str = "apt-server"
    log_level: str = "INFO"
    docs_enabled: bool = False

    # Database
    database_url: str = "postgresql://localhost:5432/apt_server"
    database_echo: bool = False

    # OAuth2 / OIDC
    oauth2_issuer: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_swagger_client_id: str = ""
    oauth2_trusted_issuers: str = ""
    oauth2_client_cache_ttl: int = 300
    token_introspection_cache_ttl: int = 60
    jwks_cache_ttl: int = 3600
    userinfo_cache_ttl: int = 300

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

    # Redis (for auth cache)
    redis_url: str = ""
    redis_key_prefix: str = "apt_server"

    # APT repository
    apt_components: str = "main"
    apt_public_components: str = "main"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def apt_components_list(self) -> list[str]:
        return [s.strip() for s in self.apt_components.split(",") if s.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def apt_public_components_list(self) -> list[str]:
        return [s.strip() for s in self.apt_public_components.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Systemd credentials take priority over .env for secrets.
    If no credential is found, Pydantic loads from .env as usual.
    """
    overrides = {}
    for env_name, field_name in [
        ("OAUTH2_CLIENT_SECRET", "oauth2_client_secret"),
    ]:
        cred = get_credential(env_name)
        if cred:
            overrides[field_name] = cred
    return Settings(**overrides)


settings = get_settings()
