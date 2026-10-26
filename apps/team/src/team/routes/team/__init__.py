# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Team API routes."""

from team.routes.team import agents, conversations, messages, teams

__all__ = [
    "agents",
    "conversations",
    "messages",
    "teams",
]
