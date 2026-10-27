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

    # OAuth2
    authorization_code_expiry_minutes: int = 10  # Authorization code validity
    access_token_expiry_minutes: int = 60  # Access token validity (1 hour)
    refresh_token_expiry_days: int = 30  # Refresh token validity (30 days)
    id_token_expiry_minutes: int = 60  # ID token validity (1 hour)
    # Group scopes: a client allowed the group scope may request any scope of the listed
    # resources, e.g. {"suite:*": ["notes", "tasks"]} lets "notes:read" through. JSON in the
    # environment. Empty by default: the groups are a deployment choice.
    scope_groups: dict[str, list[str]] = {}

    # Device Authorization (RFC 8628)
    device_code_expiry_minutes: int = 15  # Device code validity
    device_code_interval: int = 5  # Minimum polling interval in seconds

    # Pushed Authorization Requests (RFC 9126)
    par_request_expiry_seconds: int = 60  # PAR request_uri validity (1 minute)

    # Multi-tenancy
    tenant_base_domain: str = ""  # Base domain for tenant subdomains (e.g., "auth.example.com")
    tenant_custom_domain_lookup: bool = True  # Enable custom domain (CNAME) lookup

    # Custom domain provisioning
    custom_domain_cname_target: str = (
        ""  # CNAME target for custom domains (e.g., "auth.example.com")
    )
    custom_domain_nginx_sites_dir: str = "/etc/nginx/sites-enabled"  # Nginx sites directory
    custom_domain_nginx_template: str = ""  # Path to nginx template (empty = use built-in)
    custom_domain_nginx_ipv4: str = ""  # IPv4 address for nginx listen (e.g., "203.0.113.10")
    custom_domain_nginx_ipv6: str = ""  # IPv6 address for nginx listen (e.g., "2001:db8::10")
    custom_domain_upstream_socket: str = "/run/auth/auth.sock"  # Unix socket for upstream
    custom_domain_certbot_enabled: bool = True  # Enable automatic SSL via certbot
    custom_domain_certbot_email: str = ""  # Email for certbot notifications
    custom_domain_dns_check_interval_minutes: int = 5  # How often to check pending domains

    # Templates
    templates_path: str = str(Path(__file__).parent / "templates")  # Templates directory

    # File uploads
    upload_directory: str = "uploads"  # Directory for uploaded files
    upload_max_size_mb: int = 5  # Maximum file size in MB
    upload_allowed_types: str = "image/jpeg,image/png,image/gif,image/webp"  # Allowed MIME types

    # Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str | None = None  # Disabled by default (fire-and-forget tasks)

    # Cleanup tasks
    unverified_user_expiry_days: int = 3  # Days before unverified users are deleted
    orphan_avatar_cleanup_enabled: bool = True  # Enable/disable orphan avatar cleanup

    # Outbound tenant webhooks
    webhook_delivery_timeout_seconds: int = 10  # HTTP timeout per attempt
    webhook_max_attempts: int = 5  # Retries before giving up
    webhook_retention_days: int = 30  # Delete delivery rows older than this
    webhook_retention_max_per_hook: int = 1000  # Cap rows per webhook
    webhook_response_body_max_bytes: int = 8192  # Truncate captured response body
    webhook_allow_private_networks: bool = False  # SSRF escape hatch (dev only)

    # Catalog of the scopes, roles and client grants of the other services (`auth catalog sync`)
    catalog_file: str = ""  # Path of the JSON catalog file (empty = pass --file to the command)

    # Platform bootstrap (`auth bootstrap`): the tenant of the main domain and the Swagger UI client
    platform_tenant_slug: str = "platform"  # Slug of the platform tenant, when it must be created
    platform_tenant_display_name: str = "Platform"  # Display name of the platform tenant
    platform_tenant_id: str = ""  # UUID of the platform tenant to create (empty = generated)
    # Branding of the platform tenant, created once (JSON object keyed by TenantBranding columns,
    # e.g. {"primary_color": "#0055aa", "logo_url": "https://..."}). Empty = no branding row.
    platform_tenant_branding: dict[str, str] = {}
    # Redirect URIs of the Swagger UI client: the path of the docs redirect page of this service,
    # or absolute URLs when the service is reached through another origin.
    swagger_redirect_uris: list[str] = ["/docs/oauth2-redirect"]

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
