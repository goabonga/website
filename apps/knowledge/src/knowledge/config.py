# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Systemd credentials are stored in $CREDENTIALS_DIRECTORY when the service
    is started with LoadCredentialEncrypted. Falls back to environment variables
    for local development.
    """
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creds_dir:
        cred_file = Path(creds_dir) / name
        if cred_file.exists():
            return cred_file.read_text().strip()
    return os.environ.get(name, default)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Knowledge API"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = False

    # CORS
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]

    # Database
    database_url: str = "postgresql+asyncpg://knowledge:knowledge@localhost:5440/knowledge_test"

    # Redis
    redis_url: str = "redis://localhost:6387/0"
    redis_key_prefix: str = "knowledge"

    # Celery
    celery_broker_url: str = "redis://localhost:6387/0"
    celery_result_backend: str = "redis://localhost:6387/1"
    celery_queue: str = "knowledge"  # queue the application publishes to; workers must consume it
    celery_timezone: str = "UTC"
    celery_task_time_limit: int = 300  # seconds a task may run
    deletion_check_interval: float = 3600.0  # seconds between the scheduled deletion passes

    # OAuth2/OIDC (via auth service)
    oauth2_issuer: str = ""  # e.g., https://auth.example.com

    # Public client (Swagger UI) - uses PKCE, no secret
    oauth2_swagger_client_id: str = ""

    # Confidential client (API server) - for token exchange & introspection
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Token caching
    oauth2_token_cache_ttl: int = 300  # 5 minutes for token exchange
    oauth2_introspection_cache_ttl: int = 60  # 1 minute for introspection
    oauth2_trusted_issuers: str = ""
    jwks_cache_ttl: int = 3600

    # Public client (Web UI) - uses PKCE for browser login
    oauth2_frontend_client_id: str = ""

    # OpenAI (for embeddings)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Search
    default_similarity_threshold: float = 0.7
    default_search_limit: int = 10
    max_search_limit: int = 100

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds

    # Quota limits of the plans, by plan slug ("*" applies to every other plan), for example
    # {"free": {"max_collections": 3}, "*": {"max_collections": 1}}. A limit that is not listed
    # is 0 (nothing allowed) and -1 means unlimited. Empty by default: the deployment decides.
    quota_fallback_limits: dict[str, dict[str, int]] = {}

    # Multi-Tenancy
    tenant_base_domain: str = ""  # Base domain for subdomain resolution (e.g., example.com)
    tenant_custom_domain_lookup: bool = True  # Enable custom domain CNAME resolution

    # Billing service (platform billing, shared by several SaaS applications)
    billing_api_url: str = ""  # HTTP URL of the billing service; empty = not configured
    billing_socket_path: str = ""  # Unix socket of the billing service (alternative to the URL)
    billing_app_slug: str = ""  # slug of this SaaS application in billing (plans)
    billing_saas_id: str = ""  # id of this SaaS application in billing: required to use billing
    billing_client_id: str = ""  # OAuth2 client of the service calls; empty = oauth2_client_id
    billing_client_secret: str = ""  # its secret; empty = oauth2_client_secret
    billing_cache_ttl: int = 300  # seconds the plans are cached
    billing_webhook_secret: str = ""  # signs the billing webhooks: required to accept them
    billing_event_ttl: int = 604800  # seconds a processed billing event id is remembered
    billing_failure_backoff: int = 30  # seconds the fail-safe limits apply after a billing failure
    # Where Stripe sends the customer back after a checkout: both must be covered by the
    # checkout URL allow-list of the SaaS application in billing
    billing_checkout_success_url: str = ""
    billing_checkout_cancel_url: str = ""

    # Calls to the platform services (billing, mailler, custom domains)
    service_timeout: float = 10.0  # seconds

    # Custom domains (Enterprise plan): registered in the custom-domain service, which owns
    # DNS verification, certificates and the web server configuration
    custom_domain_service_url: str = ""  # HTTP URL of the custom-domain service
    custom_domain_service_socket_path: str = ""  # Unix socket of the service (alternative)
    custom_domain_client_id: str = ""  # OAuth2 client registered there; empty = oauth2_client_id
    custom_domain_client_secret: str = ""  # its secret; empty = oauth2_client_secret
    custom_domain_cname_target: str = ""  # CNAME shown before a domain is registered (hint)
    custom_domain_webhook_secret: str = ""  # signs the status webhooks: required to accept them
    custom_domain_webhook_tolerance: int = 300  # seconds a signed timestamp may be off (replay)
    custom_domain_event_ttl: int = 604800  # seconds a processed delivery id is remembered
    custom_domain_reconcile_interval: float = 300.0  # seconds between two status polls

    # GitHub Webhooks
    github_webhook_secret: str = ""  # Secret for verifying GitHub webhook signatures

    # Mailler service (platform email service): every email is sent through it, with a
    # template that the deployment imported for this application's client
    mailler_url: str = ""  # HTTP base URL of the mailler service; empty = not configured
    mailler_socket_path: str = ""  # Unix socket of the mailler service (alternative to the URL)
    mailler_client_id: str = ""  # OAuth2 client registered in mailler; empty = oauth2_client_id
    mailler_client_secret: str = ""  # its secret; empty = oauth2_client_secret
    mailler_max_retries: int = 3  # retries of an email task after a failure that can pass
    mailler_retry_delay: int = 60  # seconds before the first retry, doubled each time

    # Web UI settings
    app_base_url: str = ""  # Public URL of the application, e.g. https://knowledge.example.com
    cookie_secure: bool = True  # Set False for local dev without HTTPS
    cookie_domain: str = ""  # Leave empty for same-domain

    # The operator of the service, shown on the legal pages and the pricing page. Empty
    # values are left out of the pages.
    operator_name: str = ""  # who publishes the service (legal notice)
    contact_email: str = ""  # general contact
    sales_email: str = ""  # "contact sales" of the plans with a custom price
    legal_email: str = ""  # legal notice and terms of service
    privacy_email: str = ""  # privacy policy and data subject requests
    support_url: str = ""  # where the customers of a deleted workspace can get help


# Secrets that can be delivered as systemd credentials or environment variables.
CREDENTIAL_FIELDS = {
    "openai_api_key": "OPENAI_API_KEY",
    "oauth2_client_secret": "OAUTH2_CLIENT_SECRET",
    "billing_client_secret": "BILLING_CLIENT_SECRET",
    "billing_webhook_secret": "BILLING_WEBHOOK_SECRET",
    "mailler_client_secret": "MAILLER_CLIENT_SECRET",
    "github_webhook_secret": "GITHUB_WEBHOOK_SECRET",
    "custom_domain_client_secret": "CUSTOM_DOMAIN_CLIENT_SECRET",
    "custom_domain_webhook_secret": "CUSTOM_DOMAIN_WEBHOOK_SECRET",
}


def docs_context(request) -> dict[str, bool]:
    """Template context of every page: whether the API documentation is served.

    The pages link to the documentation only when ``DOCS_ENABLED`` is set; otherwise the
    link would lead to a 404.
    """
    return {"docs_enabled": get_settings().docs_enabled}


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance with credential overrides for secrets.

    A secret only overrides the setting when a credential or an environment variable
    provides it, so that a value from the `.env` file stays in effect otherwise.
    """
    settings = Settings()
    for field, name in CREDENTIAL_FIELDS.items():
        value = get_credential(name)
        if value:
            setattr(settings, field, value)
    return settings
