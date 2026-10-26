# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the idempotency of the sending requests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from mailler.services.idempotency import HEADER, find_replay, replay_response


def _db(existing):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute.return_value = result
    return db


def _email(**fields):
    email = MagicMock()
    email.id = uuid4()
    email.to_email = "user@example.com"
    email.scheduled_at = None
    email.task_id = "task-1"
    for key, value in fields.items():
        setattr(email, key, value)
    return email


class TestFindReplay:
    async def test_without_a_key_nothing_is_looked_up(self):
        db = _db(_email())
        assert await find_replay(db, "app-one", None, "user@example.com") is None
        db.execute.assert_not_called()

    async def test_unknown_key(self):
        assert await find_replay(_db(None), "app-one", "key-1", "user@example.com") is None

    async def test_known_key(self):
        existing = _email()
        assert await find_replay(_db(existing), "app-one", "key-1", "USER@example.com") is existing

    async def test_the_key_is_scoped_to_the_client(self):
        db = _db(None)
        await find_replay(db, "app-one", "key-1", "user@example.com")
        params = db.execute.await_args.args[0].compile().params
        assert params["client_id_1"] == "app-one"
        assert params["idempotency_key_1"] == "key-1"

    async def test_clients_without_identity_are_matched_on_no_client(self):
        db = _db(None)
        await find_replay(db, None, "key-1", "user@example.com")
        sql = str(db.execute.await_args.args[0].compile())
        assert "emails.client_id IS NULL" in sql

    async def test_key_reused_for_another_recipient(self):
        with pytest.raises(HTTPException) as exc_info:
            await find_replay(_db(_email()), "app-one", "key-1", "other@example.com")
        assert exc_info.value.status_code == 422
        assert HEADER in exc_info.value.detail


class TestReplayResponse:
    def test_immediate_email(self):
        email = _email()
        response = replay_response(email)
        assert response.id == str(email.id)
        assert response.status == "queued"
        assert response.task_id == "task-1"
        assert "Already submitted" in response.message

    def test_scheduled_email(self):
        response = replay_response(_email(scheduled_at=datetime.now(UTC), task_id=None))
        assert response.status == "scheduled"
        assert response.task_id is None
