# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., OPENAI_API_KEY).
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
    app_name: str = "GOABONGA API"
    debug: bool = False
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql://localhost/app"

    # Redis
    redis_url: str = ""  # Uses prompt_cache_redis_url if empty
    redis_key_prefix: str = "fastapi"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # OpenAI configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # RAG configuration
    rag_embedding_model: str = "text-embedding-3-small"
    rag_similarity_threshold: float = 0.7
    rag_max_results: int = 5

    # Prompt configuration
    prompt_cache_redis_url: str = "redis://localhost:6379/4"
    prompt_cache_ttl: int = 300  # Cache TTL in seconds (0 = no expiration)

    # Rate limiting
    rate_limit_redis_url: str = "redis://localhost:6379/1"
    rate_limit_anon: int = 10  # requests per window for anonymous users
    rate_limit_auth: int = 60  # requests per window for authenticated users
    rate_limit_window: int = 60  # window size in seconds

    # Session configuration
    session_redis_url: str = "redis://localhost:6379/2"
    session_redis_ttl: int = 3600  # 1 hour TTL for session data
    conversation_cache_ttl: int = 1800  # 30 minutes TTL for conversation cache
    conversation_sync_interval: int = 30  # sync dirty conversations every N seconds

    # Session creation rate limiting (anti-abuse)
    session_create_limit: int = 3  # max new sessions per IP per window
    session_create_window: int = 86400  # 24 hours window for session creation

    # OAuth2 / OIDC
    oauth2_issuer: str = ""
    oauth2_swagger_client_id: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_trusted_issuers: str = ""
    oauth2_client_cache_ttl: int = 300  # Cache exchanged scopes (seconds)
    token_introspection_cache_ttl: int = 60  # Cache introspection results (seconds)
    jwks_cache_ttl: int = 3600

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
settings = Settings(
    openai_api_key=get_credential("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET",
        os.environ.get("OAUTH2_CLIENT_SECRET", ""),
    ),
)
