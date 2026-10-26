# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., JWKS_ENCRYPTION_KEY).
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
    """Application settings."""

    # Logging
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # API documentation (Swagger UI at /docs)
    app_title: str = "OIDC/OAuth2 Service"  # Title of the OpenAPI document and of the docs page
    swagger_client_id: str = "swagger-ui"  # client_id the Swagger UI "Authorize" button uses
    swagger_scopes: str = "openid profile email"  # Space-separated scopes it requests

    # Database (supports postgresql://, postgres://, postgresql+asyncpg://)
    database_url: str = "postgresql://localhost:5432/auth"

    # Database pool settings
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # OIDC / OAuth2
    issuer: str | None = None  # Auto-detected from request if not set

    # JWKS
    jwks_encryption_key: str = ""  # Base64-encoded 32-byte key for AES-256-GCM
    jwks_key_size: int = 2048  # RSA key size in bits
    jwks_rotation_days: int = 90  # Rotate keys every N days
    jwks_grace_period_days: int = 30  # Keep revoked keys for validation

    # Email backend
    email_backend: str = "smtp"  # "smtp" or "mailler"

    # Email / SMTP
    smtp_host: str = ""  # SMTP server hostname (empty = log to console)
    smtp_port: int = 587  # SMTP server port
    smtp_tls: bool = True  # Use TLS
    smtp_user: str = ""  # SMTP username
    smtp_password: str = ""  # SMTP password
    smtp_from: str = "noreply@example.com"  # From email address

    # Mailler service integration
    mailler_url: str = (
        ""  # Mailler service URL (e.g., https://mailler.internal or http://localhost for UDS)
    )
    mailler_unix_socket: str = ""  # Unix socket path (e.g., /run/mailler/mailler.sock)
    mailler_provider: str = "brevo"  # Default email provider (brevo, sendgrid, ses, protonmail)
    mailler_client_id: str = ""  # OAuth2 client ID for mailler authentication
    mailler_client_secret: str = ""  # OAuth2 client secret for mailler authentication
    mailler_auth_url: str = (
        ""  # Auth service URL for token endpoint (e.g., https://auth.example.com)
    )

    # Verification
    verification_code_expiry_hours: int = 24  # Verification code validity

    # Password Reset
    password_reset_expiry_hours: int = 1  # Password reset token validity

    # Session
    session_expiry_days: int = 7  # Session validity in days
    session_cookie_name: str = "session"  # Session cookie name
    session_cookie_secure: bool = True  # Secure cookie (HTTPS only)

    # MFA
    mfa_issuer_name: str = "Auth"  # Issuer name shown in authenticator apps
    mfa_email_code_expiry_minutes: int = 10  # MFA email code validity in minutes

    # Multi-tenancy
    tenant_base_domain: str = ""  # Base domain for tenant subdomains (e.g., "auth.example.com")
    tenant_custom_domain_lookup: bool = True  # Enable custom domain (CNAME) lookup

    # Templates
    templates_path: str = str(Path(__file__).parent / "templates")  # Templates directory

    # File uploads
    upload_directory: str = "uploads"  # Directory for uploaded files
    upload_max_size_mb: int = 5  # Maximum file size in MB
    upload_allowed_types: str = "image/jpeg,image/png,image/gif,image/webp"  # Allowed MIME types

    # Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str | None = None  # Disabled by default (fire-and-forget tasks)

    # Outbound tenant webhooks
    webhook_delivery_timeout_seconds: int = 10  # HTTP timeout per attempt
    webhook_max_attempts: int = 5  # Retries before giving up
    webhook_retention_days: int = 30  # Delete delivery rows older than this
    webhook_retention_max_per_hook: int = 1000  # Cap rows per webhook
    webhook_response_body_max_bytes: int = 8192  # Truncate captured response body
    webhook_allow_private_networks: bool = False  # SSRF escape hatch (dev only)

    model_config = SettingsConfigDict(env_file=".env")


# Load settings with credential overrides for secrets
settings = Settings(
    jwks_encryption_key=get_credential(
        "JWKS_ENCRYPTION_KEY", os.environ.get("JWKS_ENCRYPTION_KEY", "")
    ),
    smtp_password=get_credential("SMTP_PASSWORD", os.environ.get("SMTP_PASSWORD", "")),
    mailler_client_secret=get_credential(
        "MAILLER_CLIENT_SECRET", os.environ.get("MAILLER_CLIENT_SECRET", "")
    ),
)
