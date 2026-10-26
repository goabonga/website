# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration using Pydantic Settings."""

import os
from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """A setting that an operation needs is empty."""


def require_setting(name: str, source: object | None = None) -> str:
    """Return the value of a setting that has no default, or fail with its variable name.

    Args:
        name: Attribute name on the settings object
        source: Settings object to read (defaults to the application settings)

    Raises:
        ConfigurationError: If the setting is empty
    """
    value = getattr(source if source is not None else settings, name)
    if not value:
        raise ConfigurationError(f"{name.upper()} is not configured")
    return str(value)


def get_credential(name: str, default: str = "") -> str:
    """Read credential from systemd credentials directory or environment.

    Args:
        name: Credential name
        default: Default value if not found

    Returns:
        Credential value
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


class TokenValidationMode(StrEnum):
    """Token validation modes."""

    JWT_ONLY = "jwt_only"
    INTROSPECTION = "introspection"
    TOKEN_EXCHANGE = "token_exchange"


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

    # Redis
    redis_url: str = "redis://localhost:6379/13"
    redis_key_prefix: str = "custom-domain"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_queue: str = "custom-domain"
    celery_task_soft_time_limit_seconds: int = 270
    celery_task_time_limit_seconds: int = 300

    # Nginx (paths and binaries have no default: a deployment must provide them)
    nginx_sites_dir: str = ""
    nginx_config_prefix: str = "custom-domain-"
    nginx_ipv4: str | None = None
    nginx_ipv6: str | None = None
    nginx_bin: str = ""
    nginx_service: str = "nginx"
    systemctl_bin: str = ""

    # Certbot
    certbot_enabled: bool = True
    certbot_email: str = ""
    certbot_bin: str = ""
    openssl_bin: str = ""
    certbot_webroot: str = ""
    letsencrypt_dir: str = ""
    certbot_revoke_on_deprovision: bool = True

    # Provisioning
    provisioning_max_retries: int = 2
    provisioning_retry_delay_seconds: int = 600
    event_history_size: int = 100
    event_history_ttl_seconds: int = 86400

    # Privileged operations (see services/privileged.py)
    sudo_bin: str = "sudo"
    privileged_helper: str = ""
    privileged_staging_dir: str = ""
    privileged_timeout_seconds: int = 120
    template_validation_timeout_seconds: int = 30

    # DNS verification
    dns_check_interval_minutes: int = 5
    dns_timeout_seconds: int = 10
    dns_verification_max_retries: int = 3
    dns_verification_retry_delay_seconds: int = 300

    # Domain defaults (used when neither the request nor the client provides a value)
    default_cname_target: str = ""

    # Domain lifecycle
    certificate_renewal_days: int = 30
    domain_activation_timeout_hours: int = 48
    domain_health_check_interval_hours: int = 24
    domain_health_check_minute: int = 30
    soft_delete_purge_days: int = 30

    # Periodic tasks (five-field cron expressions: minute hour day-of-month month day-of-week)
    certificate_expiry_check_cron: str = "0 2 * * *"
    stale_cleanup_cron: str = "0 4 * * *"
    purge_deleted_cron: str = "0 5 * * 0"

    # Webhooks sent to the clients
    webhook_timeout_seconds: int = 10
    webhook_max_retries: int = 5
    webhook_retry_delay_seconds: int = 60
    webhook_allow_insecure_urls: bool = False

    # Templates
    templates_dir: str = "custom_domain/templates"

    # SSE
    sse_heartbeat_interval: int = 30
    sse_poll_interval_seconds: float = 1.0

    # OAuth2 / OIDC
    oauth2_issuer: str = ""
    admin_scope: str = "custom-domain:admin"
    oauth2_swagger_client_id: str = ""
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_trusted_issuers: str = ""
    oauth2_client_cache_ttl: int = 300
    oauth2_http_timeout_seconds: float = 10.0
    token_introspection_cache_ttl: int = 60
    token_validation_mode: TokenValidationMode = TokenValidationMode.INTROSPECTION
    token_exchange_cache_ttl: int = 300
    jwks_cache_ttl: int = 3600
    oauth2_introspection_endpoint: str | None = None
    oauth2_token_endpoint: str | None = None
    oauth2_jwks_uri: str | None = None

    @property
    def base_dir(self) -> Path:
        """Get the directory that contains the application package."""
        return Path(__file__).parent.parent


# Load settings with credential support
settings = Settings(
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET", os.environ.get("OAUTH2_CLIENT_SECRET", "")
    ),
)
