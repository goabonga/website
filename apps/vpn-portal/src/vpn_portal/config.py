# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Application configuration."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_credential(name: str, default: str = "") -> str:
    """Read a secret from systemd credentials or environment.

    Args:
        name: Credential name (e.g., OAUTH2_CLIENT_SECRET).
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
    """Application settings, read from the environment and an optional ``.env`` file."""

    # Application
    app_name: str = "VPN Portal"
    debug: bool = False
    docs_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://localhost:5432/vpn_portal"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # Step-CA configuration
    stepca_url: str = "https://127.0.0.1:8443"
    stepca_root_ca: str = "/etc/step-ca/certs/root_ca.crt"
    stepca_provisioner: str = "vpn-portal"
    stepca_provisioner_password: str = ""
    stepca_provisioner_password_file: str = "/etc/step-ca/secrets/vpn-portal-password"

    # Certificate settings
    cert_default_duration_minutes: int = 10
    cert_max_duration_minutes: int = 15

    # OAuth2 / OIDC configuration
    oauth2_issuer: str = ""  # OIDC issuer URL (e.g., https://auth.example.com)
    oauth2_swagger_client_id: str = ""  # OAuth2 PKCE client ID for Swagger UI

    # OAuth2 confidential client for token exchange (RFC 8693)
    oauth2_client_id: str = ""
    oauth2_client_secret: str = ""

    # Redis for token exchange and introspection cache
    redis_url: str = ""  # e.g., unix:///run/redis/redis.sock?db=8
    redis_key_prefix: str = "vpn"  # Cache key prefix for auth tokens
    oauth2_client_cache_ttl: int = 300  # 5 minutes

    # Token introspection cache (RFC 7662)
    token_introspection_cache_ttl: int = 60  # seconds

    # JWKS cache TTL (seconds)
    jwks_cache_ttl: int = 3600  # 1 hour

    # Trusted issuers (comma-separated, in addition to oauth2_issuer)
    oauth2_trusted_issuers: str = ""

    # OpenVPN configuration
    openvpn_server: str = "vpn.example.com"
    openvpn_port: int = 1194
    openvpn_proto: str = "udp"
    openvpn_ca_path: str = "/etc/openvpn/server/ca.crt"
    openvpn_ta_key_path: str = "/etc/openvpn/server/ta.key"

    # RBAC: Scope to routes mapping
    # Format: {"scope": ["route1", "route2"]}
    scope_routes: dict[str, list[str]] = {
        "vpn:connect": ["10.8.0.0/24"],
        "vpn:internal": ["10.8.0.0/24", "10.0.0.0/8"],
        "vpn:infrastructure": ["10.8.0.0/24", "192.168.0.0/16"],
        "vpn:development": ["10.8.0.0/24", "10.100.0.0/16"],
        "vpn:production": ["10.8.0.0/24", "10.200.0.0/16"],
    }

    # Default routes for all authenticated users
    default_routes: list[str] = ["10.8.0.0/24"]

    model_config = SettingsConfigDict(env_file=".env")


# Load settings with credential overrides for secrets
settings = Settings(
    stepca_provisioner_password=get_credential(
        "STEPCA_PROVISIONER_PASSWORD",
        os.environ.get("STEPCA_PROVISIONER_PASSWORD", ""),
    ),
    oauth2_client_secret=get_credential(
        "OAUTH2_CLIENT_SECRET",
        os.environ.get("OAUTH2_CLIENT_SECRET", ""),
    ),
)
