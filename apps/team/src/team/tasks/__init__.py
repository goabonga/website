# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Celery tasks."""

from team.tasks.agent_runner import run_agent_task

__all__ = [
    "run_agent_task",
]
