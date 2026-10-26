# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Enumerations for the custom domain service."""

from enum import StrEnum


class DomainStatus(StrEnum):
    """Status of a custom domain."""

    PENDING = "pending"
    DNS_VERIFYING = "dns_verifying"
    DNS_VERIFIED = "dns_verified"
    SSL_PROVISIONING = "ssl_provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    DEPROVISIONING = "deprovisioning"


class ProvisioningStep(StrEnum):
    """Steps in the provisioning process."""

    DNS_CHECK = "dns_check"
    NGINX_HTTP = "nginx_http"
    CERTBOT = "certbot"
    NGINX_HTTPS = "nginx_https"
