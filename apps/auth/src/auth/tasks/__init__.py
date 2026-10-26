# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks."""

# Import all task modules so Celery can discover them
from auth.tasks import (
    backfill_pairwise,  # noqa: F401
    cleanup,  # noqa: F401
    custom_domain,  # noqa: F401
    email,  # noqa: F401
    webhooks,  # noqa: F401
)
