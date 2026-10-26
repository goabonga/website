# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Conftest for route tests."""

from unittest.mock import MagicMock, patch

import pytest
from internal.tasks.knowledge_generation import generate_knowledge_entries
from internal.tasks.knowledge_validation import validate_knowledge_entry


@pytest.fixture(autouse=True)
def mock_celery_validation_task():
    """Prevent Celery from connecting to Redis during route tests.

    Routes dispatch validate_knowledge_entry.delay() which attempts to connect
    to the Redis broker. Without this mock, each affected test waits ~19s for
    the connection timeout.

    Uses patch.object so the ``from ... import`` line in the route is still
    covered (it imports the real task object, only .delay is mocked).
    """
    with patch.object(validate_knowledge_entry, "delay") as mock_delay:
        yield mock_delay


@pytest.fixture(autouse=True)
def mock_celery_generation_task():
    """Prevent Celery from connecting to Redis for generation task dispatch."""
    mock_result = MagicMock()
    mock_result.id = "test-task-id-123"
    with patch.object(generate_knowledge_entries, "delay", return_value=mock_result) as mock_delay:
        yield mock_delay
