# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks."""

from custom_domain.tasks.provisioning import deprovision_domain, provision_domain_ssl

__all__ = [
    "deprovision_domain",
    "provision_domain_ssl",
]
