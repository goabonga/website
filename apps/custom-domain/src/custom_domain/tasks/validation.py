# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Validation tasks that need the privileged helper."""

from custom_domain.celery import celery_app
from custom_domain.logging import get_logger
from custom_domain.services.template import template_service
from custom_domain.tasks.provisioning import run_async

logger = get_logger(__name__)


@celery_app.task
def validate_nginx_template(config: str) -> dict:
    """Check rendered nginx configuration with ``nginx -t``.

    Runs in the worker because the check goes through the privileged helper, which
    the API process can not start.

    Returns:
        ``{"valid": bool, "error": str}``
    """
    valid, error = run_async(template_service.validate_nginx_syntax(config))
    return {"valid": valid, "error": error}
