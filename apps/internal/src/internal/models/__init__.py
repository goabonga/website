# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database models for internal application."""

from internal.models.conversation import Conversation, Message

__all__ = [
    "Conversation",
    "Message",
]
