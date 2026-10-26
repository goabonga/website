# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks for Mailler."""

# Import tasks explicitly so they are registered with Celery
from mailler.tasks.send import send_email_task  # noqa: F401
