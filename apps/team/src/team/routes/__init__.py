# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""API routes."""

from team.routes import health
from team.routes.team import agents, conversations, memory, messages, tasks, teams, workflows

__all__ = [
    "health",
    "agents",
    "conversations",
    "memory",
    "messages",
    "tasks",
    "teams",
    "workflows",
]
