# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the anonymous session feature."""

from unittest.mock import AsyncMock, MagicMock, patch

from backend.auth.models import User
from backend.database import get_db
from backend.middleware.rate_limit import get_rate_limiter
from backend.session import dependencies
from backend.session.dependencies import ChatContext, get_chat_context
from behave import given, then, when
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient


@given('an API exposing the chat context at "{path}"')
def step_context_api(context, path):
    api = FastAPI()

    @api.get(path)
    async def show(chat: ChatContext = Depends(get_chat_context)):
        return {
            "user_id": str(chat.user_id) if chat.user_id else None,
            "session_id": chat.session_id,
            "is_authenticated": chat.is_authenticated,
            "session_created": chat.session_created,
            "anonymous_session_id": chat.anonymous_session_id,
        }

    context.limiter = MagicMock()
    context.limiter.check_session_creation_limit = AsyncMock(return_value=(True, 3, 86400))
    context.limiter.record_session_creation = AsyncMock()
    context.known_sessions = set()

    async def fake_get(session_id):
        return {"session_id": session_id} if session_id in context.known_sessions else None

    service = MagicMock()
    service.get = AsyncMock(side_effect=fake_get)
    service.create = AsyncMock()
    service.close = AsyncMock()
    patcher = patch.object(dependencies, "SessionService", return_value=service)
    patcher.start()
    context.patches["session_service"] = patcher

    api.dependency_overrides[get_db] = lambda: context.db
    api.dependency_overrides[get_rate_limiter] = lambda: context.limiter
    context.api = api
    context.client.close()
    context.client = TestClient(api, raise_server_exceptions=False)


@given("session creation is allowed")
def step_creation_allowed(context):
    context.limiter.check_session_creation_limit.return_value = (True, 3, 86400)


@given("session creation is refused")
def step_creation_refused(context):
    context.limiter.check_session_creation_limit.return_value = (False, 0, 86400)


@given('the session "{session_id}" exists')
def step_session_exists(context, session_id):
    context.known_sessions.add(session_id)


@given('I am the authenticated user "{user_id}"')
def step_authenticated(context, user_id):
    user = User(id=user_id, scopes=["openid"])
    context.api.dependency_overrides[dependencies._get_optional_user] = lambda: user


@when('I request "{path}" with the session cookie "{value}"')
def step_get_with_cookie(context, path, value):
    context.client.cookies.set("session_id", value)
    context.response = context.client.get(path)


@then("a session creation should have been recorded")
def step_recorded(context):
    context.limiter.record_session_creation.assert_awaited_once()


@then("no session creation should have been recorded")
def step_not_recorded(context):
    context.limiter.record_session_creation.assert_not_awaited()
