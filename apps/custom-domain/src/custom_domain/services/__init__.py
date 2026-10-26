# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Services module."""

from custom_domain.services.nginx import nginx_manager
from custom_domain.services.template import TemplateValidationResult, template_service

__all__ = [
    "nginx_manager",
    "template_service",
    "TemplateValidationResult",
]
