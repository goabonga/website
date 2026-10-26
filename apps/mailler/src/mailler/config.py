# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Configuration settings for Mailler API."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Mailler API"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_echo: bool = False

    # CORS
    cors_origins: list[str] = []  # no origin is allowed until configured
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql:///mailler"

    # Redis
    redis_url: str = "redis://localhost:6379/11"
    redis_key_prefix: str = "mailler"  # Cache key prefix for auth tokens

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_queue: str = "mailler"  # queue the workers consume (-Q)

    # Delivery retries
    send_max_retries: int = 3  # attempts before an email is marked as failed
    send_retry_delay: int = 60  # seconds before the first retry
    send_retry_backoff_max: int = 300  # upper bound of the exponential backoff, in seconds

    # Scheduler
    stuck_email_minutes: int = 5  # a pending email older than this is queued again
    stuck_email_batch: int = 50  # stuck emails queued again per run
    scheduled_email_batch: int = 100  # due scheduled emails queued per run
    email_retention_days: int = 90  # emails older than this are deleted

    # Campaigns
    campaign_batch_size: int = 50  # contacts processed between two checks for a pause
    default_provider: str = ""  # optional platform provider, used when nothing else is set

    # Default sender
    default_from: str = ""  # optional platform sender, used when the caller has none
    default_from_name: str = ""

    # Brevo
    brevo_api_key: str = ""

    # SendGrid
    sendgrid_api_key: str = ""

    # AWS SES
    ses_region: str = ""
    ses_access_key: str = ""
    ses_secret_key: str = ""

    # Protonmail Bridge (SMTP)
    protonmail_host: str = ""
    protonmail_port: int = 0
    protonmail_user: str = ""
    protonmail_password: str = ""

    # Webhook HMAC signature (shared secret with webhooks service)
    webhook_hmac_secret: str = ""

    # Unsubscribe settings
    unsubscribe_base_url: str = ""  # public base URL of the API, e.g. https://mailer.example/api/v1

    # OAuth2 / OIDC
    oauth2_issuer: str = ""  # empty disables authentication (503)
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""
    oauth2_swagger_client_id: str = ""
    admin_scope: str = "mailler:admin"  # scope allowing a caller to cross the client boundary
    oauth2_trusted_issuers: str = ""  # Comma-separated additional trusted issuers
    oauth2_client_cache_ttl: int = 300
    token_introspection_cache_ttl: int = 60
    jwks_cache_ttl: int = 3600  # 1 hour


# Load settings with credential support
settings = Settings(
    brevo_api_key=get_credential("BREVO_API_KEY", os.environ.get("BREVO_API_KEY", "")),
    sendgrid_api_key=get_credential("SENDGRID_API_KEY", os.environ.get("SENDGRID_API_KEY", "")),
    ses_access_key=get_credential("SES_ACCESS_KEY", os.environ.get("SES_ACCESS_KEY", "")),
    ses_secret_key=get_credential("SES_SECRET_KEY", os.environ.get("SES_SECRET_KEY", "")),
    protonmail_password=get_credential(
        "PROTONMAIL_PASSWORD", os.environ.get("PROTONMAIL_PASSWORD", "")
    ),
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET", os.environ.get("OAUTH2_CLIENT_SECRET", "")
    ),
    webhook_hmac_secret=get_credential(
        "WEBHOOK_HMAC_SECRET", os.environ.get("WEBHOOK_HMAC_SECRET", "")
    ),
)
