# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.auth.logout — Logout endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_user

MODULE = "auth.api.routes.auth.logout"
TENANT_MODULE = "auth.middlewares.tenant"


def _mock_request(cookies=None):
    request = MagicMock()
    request.cookies = cookies or {}
    return request


def _mock_cookie_name():
    return "session_id"


# ---------------------------------------------------------------------------
# _clear_session_cookies
# ---------------------------------------------------------------------------


class TestClearSessionCookies:
    @patch(f"{TENANT_MODULE}.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{TENANT_MODULE}.get_csrf_cookie_name", return_value="csrf_token")
    @patch(f"{TENANT_MODULE}.get_session_cookie_name", return_value="session_id")
    def test_clears_both_cookies(self, mock_name, mock_csrf, mock_domain):
        from auth.api.routes.auth.logout import _clear_session_cookies

        response = MagicMock()
        _clear_session_cookies(response)

        assert response.delete_cookie.call_count == 2
        calls = [c.kwargs for c in response.delete_cookie.call_args_list]
        keys = [c["key"] for c in calls]
        assert "session_id" in keys
        assert "csrf_token" in keys


# ---------------------------------------------------------------------------
# logout_submit
# ---------------------------------------------------------------------------


class TestLogoutSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_with_session_revokes_and_redirects(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_submit

        user = make_user()
        request = _mock_request(cookies={"session_id": "token_abc"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        session_svc.revoke_session = AsyncMock()

        result = await logout_submit(request, db, session_svc)

        session_svc.revoke_session.assert_awaited_once_with(db, "token_abc")
        db.commit.assert_awaited_once()
        assert result.status_code == 303
        assert "/auth/login" in result.headers.get("location", "")
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_session_still_redirects(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_submit

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()

        result = await logout_submit(request, db, session_svc)

        assert result.status_code == 303
        mock_clear.assert_called_once()


# ---------------------------------------------------------------------------
# logout_api
# ---------------------------------------------------------------------------


class TestLogoutApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_success(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_api

        user = make_user()
        request = _mock_request(cookies={"session_id": "token_abc"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        session_svc.revoke_session = AsyncMock(return_value=True)

        result = await logout_api(request, db, session_svc)

        session_svc.revoke_session.assert_awaited_once_with(db, "token_abc")
        db.commit.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_session_raises_401(self, mock_cookie_name):
        from auth.api.routes.auth.logout import logout_api

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await logout_api(request, db, session_svc)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_invalid_session_raises_401(self, mock_cookie_name):
        from auth.api.routes.auth.logout import logout_api

        request = _mock_request(cookies={"session_id": "invalid"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=None)
        session_svc.revoke_session = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await logout_api(request, db, session_svc)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# logout_all_submit
# ---------------------------------------------------------------------------


class TestLogoutAllSubmit:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_with_session_revokes_all(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_all_submit

        user = make_user()
        request = _mock_request(cookies={"session_id": "token_abc"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        session_svc.revoke_all_user_sessions = AsyncMock(return_value=5)

        result = await logout_all_submit(request, db, session_svc)

        session_svc.revoke_all_user_sessions.assert_awaited_once()
        assert result.status_code == 303

    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_with_session_no_user(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_all_submit

        request = _mock_request(cookies={"session_id": "token_abc"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=None)

        result = await logout_all_submit(request, db, session_svc)

        session_svc.revoke_all_user_sessions.assert_not_called()
        assert result.status_code == 303

    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_session(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_all_submit

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()

        result = await logout_all_submit(request, db, session_svc)

        assert result.status_code == 303


# ---------------------------------------------------------------------------
# logout_all_api
# ---------------------------------------------------------------------------


class TestLogoutAllApi:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._clear_session_cookies")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_success(self, mock_cookie_name, mock_clear):
        from auth.api.routes.auth.logout import logout_all_api

        user = make_user()
        request = _mock_request(cookies={"session_id": "token_abc"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        session_svc.revoke_all_user_sessions = AsyncMock(return_value=3)

        result = await logout_all_api(request, db, session_svc)

        session_svc.revoke_all_user_sessions.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_no_session_raises_401(self, mock_cookie_name):
        from auth.api.routes.auth.logout import logout_all_api

        request = _mock_request()
        db = AsyncMock()
        session_svc = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await logout_all_api(request, db, session_svc)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session_id")
    async def test_invalid_session_raises_401(self, mock_cookie_name):
        from auth.api.routes.auth.logout import logout_all_api

        request = _mock_request(cookies={"session_id": "token"})
        db = AsyncMock()
        session_svc = MagicMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await logout_all_api(request, db, session_svc)
        assert exc_info.value.status_code == 401
