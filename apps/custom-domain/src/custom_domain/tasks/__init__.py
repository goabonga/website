# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks."""

from custom_domain.tasks.maintenance import (
    check_certificate_expiry,
    check_domain_health,
    cleanup_stale_domains,
    purge_deleted_domains,
)
from custom_domain.tasks.provisioning import deprovision_domain, provision_domain_ssl
from custom_domain.tasks.validation import validate_nginx_template
from custom_domain.tasks.verification import check_pending_domains, verify_domain_dns

__all__ = [
    "check_certificate_expiry",
    "check_domain_health",
    "check_pending_domains",
    "cleanup_stale_domains",
    "deprovision_domain",
    "provision_domain_ssl",
    "purge_deleted_domains",
    "validate_nginx_template",
    "verify_domain_dns",
]
