# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the request-scoped logging helpers in knowledge/logging.py."""

import logging
from unittest.mock import MagicMock


class TestSetRequestContext:
    """Test set_request_context (lines 110-115)."""

    def test_set_request_context_with_values(self):
        from knowledge.logging import request_context, set_request_context

        set_request_context(user_id="user-123", tenant_id="tenant-456")
        ctx = request_context.get()
        assert ctx["user_id"] == "user-123"
        assert ctx["tenant_id"] == "tenant-456"

    def test_set_request_context_defaults(self):
        from knowledge.logging import request_context, set_request_context

        set_request_context()
        ctx = request_context.get()
        assert ctx["user_id"] == "-"
        assert ctx["tenant_id"] == "-"

    def test_set_request_context_with_extra(self):
        from knowledge.logging import request_context, set_request_context

        set_request_context(user_id="u1", tenant_id="t1", request_id="req-99")
        ctx = request_context.get()
        assert ctx["request_id"] == "req-99"


class TestClearRequestContext:
    """Test clear_request_context (line 120)."""

    def test_clear_request_context(self):
        from knowledge.logging import clear_request_context, request_context, set_request_context

        set_request_context(user_id="user-123")
        clear_request_context()
        ctx = request_context.get()
        assert ctx == {}


class TestLogAction:
    """Test log_action function (lines 139-152)."""

    def test_log_action_basic(self):
        from knowledge.logging import log_action

        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "create_collection")
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "ACTION: create_collection" in call_args

    def test_log_action_with_details(self):
        from knowledge.logging import log_action

        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "delete_doc", doc_id="d123", reason="expired")
        call_args = mock_logger.info.call_args[0][0]
        assert "ACTION: delete_doc" in call_args
        assert "doc_id=d123" in call_args
        assert "reason=expired" in call_args

    def test_log_action_with_explicit_user_and_tenant(self):
        from knowledge.logging import log_action, request_context

        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "update", user_id="u-explicit", tenant_id="t-explicit")
        mock_logger.info.assert_called_once()
        # Context should have been set
        ctx = request_context.get()
        assert ctx["user_id"] == "u-explicit"
        assert ctx["tenant_id"] == "t-explicit"

    def test_log_action_uses_request_context_defaults(self):
        from knowledge.logging import log_action, set_request_context

        set_request_context(user_id="ctx-user", tenant_id="ctx-tenant")
        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "search")
        call_args = mock_logger.info.call_args[0][0]
        assert "ACTION: search" in call_args

    def test_log_action_with_user_id_only(self):
        """When only user_id is provided, tenant_id should come from context."""
        from knowledge.logging import log_action, request_context, set_request_context

        set_request_context(user_id="old", tenant_id="old-tenant")
        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "action", user_id="new-user")
        ctx = request_context.get()
        assert ctx["user_id"] == "new-user"

    def test_log_action_with_tenant_id_only(self):
        """When only tenant_id is provided, user_id should come from context."""
        from knowledge.logging import log_action, request_context, set_request_context

        set_request_context(user_id="old-user", tenant_id="old")
        mock_logger = MagicMock(spec=logging.Logger)
        log_action(mock_logger, "action", tenant_id="new-tenant")
        ctx = request_context.get()
        assert ctx["tenant_id"] == "new-tenant"
