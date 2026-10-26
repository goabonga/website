# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.middlewares.cors — OAuth2 CORS middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_http_scope(path="/oauth2/token", method="GET", origin=None):
    """Build a minimal ASGI HTTP scope dict."""
    headers = []
    if origin:
        headers.append((b"origin", origin.encode()))
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": headers,
    }


def _make_ws_scope():
    """Build a minimal ASGI WebSocket scope dict."""
    return {"type": "websocket", "path": "/ws"}


# ── __init__ ─────────────────────────────────────────────────────────────────


class TestInit:
    def test_sets_app(self):
        from auth.middlewares.cors import OAuth2CORSMiddleware

        app = AsyncMock()
        mw = OAuth2CORSMiddleware(app)
        assert mw.app is app


# ── __call__ ─────────────────────────────────────────────────────────────────


class TestCall:
    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self):
        """Non-http scopes (e.g. websocket) are forwarded to the inner app."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)

        scope = _make_ws_scope()
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        inner_app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_no_origin_passes_through(self):
        """Requests without an Origin header skip CORS processing."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)

        scope = _make_http_scope(path="/oauth2/token", origin=None)
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        inner_app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_non_cors_path_passes_through(self):
        """Requests to paths NOT in CORS_PATHS skip CORS processing."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)

        scope = _make_http_scope(path="/admin/dashboard", origin="https://app.example.com")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        inner_app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_options_preflight_calls_send_preflight(self):
        """OPTIONS on a CORS path delegates to _send_preflight_response."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        mw._send_preflight_response = AsyncMock()

        scope = _make_http_scope(
            path="/oauth2/token", method="OPTIONS", origin="https://app.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        mw._send_preflight_response.assert_awaited_once_with(
            scope, receive, send, "https://app.example.com"
        )
        inner_app.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allowed_origin_wraps_send(self):
        """When origin is allowed, send is wrapped so CORS headers get injected."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        mw._is_allowed_origin = AsyncMock(return_value=True)

        scope = _make_http_scope(
            path="/oauth2/token", method="POST", origin="https://app.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        # The inner app should have been called with a *different* send (the wrapper).
        inner_app.assert_awaited_once()
        call_args = inner_app.await_args
        wrapped_send = call_args[0][2]
        assert wrapped_send is not send

    @pytest.mark.asyncio
    async def test_disallowed_origin_no_cors_headers(self):
        """When origin is NOT allowed, send is NOT wrapped; the original send is used."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        mw._is_allowed_origin = AsyncMock(return_value=False)

        scope = _make_http_scope(
            path="/oauth2/token", method="POST", origin="https://evil.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        # The original send is passed through unchanged.
        inner_app.assert_awaited_once_with(scope, receive, send)

    @pytest.mark.asyncio
    async def test_app_exception_is_reraised(self):
        """If the inner app raises, the exception propagates up."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock(side_effect=RuntimeError("boom"))
        mw = OAuth2CORSMiddleware(inner_app)
        mw._is_allowed_origin = AsyncMock(return_value=True)

        scope = _make_http_scope(
            path="/oauth2/token", method="POST", origin="https://app.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(RuntimeError, match="boom"):
            await mw(scope, receive, send)


# ── _create_cors_send ────────────────────────────────────────────────────────


class TestCreateCorsSend:
    @pytest.mark.asyncio
    async def test_injects_cors_headers_on_response_start(self):
        """CORS headers are appended to the http.response.start message."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        original_send = AsyncMock()

        cors_send = mw._create_cors_send(original_send, "https://app.example.com", "/oauth2/token")

        message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
        await cors_send(message)

        original_send.assert_awaited_once()
        sent_message = original_send.await_args[0][0]

        assert sent_message["type"] == "http.response.start"
        assert sent_message["status"] == 200

        header_names = [h[0] for h in sent_message["headers"]]
        assert b"access-control-allow-origin" in header_names
        assert b"access-control-allow-credentials" in header_names
        assert b"access-control-expose-headers" in header_names

        # Verify the origin value is correct.
        header_dict = dict(sent_message["headers"])
        assert header_dict[b"access-control-allow-origin"] == b"https://app.example.com"
        assert header_dict[b"access-control-allow-credentials"] == b"true"
        assert header_dict[b"access-control-expose-headers"] == b"Content-Type"

    @pytest.mark.asyncio
    async def test_body_message_passes_through(self):
        """http.response.body messages are forwarded without modification."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        original_send = AsyncMock()

        cors_send = mw._create_cors_send(original_send, "https://app.example.com", "/oauth2/token")

        body_message = {"type": "http.response.body", "body": b'{"ok": true}'}
        await cors_send(body_message)

        original_send.assert_awaited_once_with(body_message)

    @pytest.mark.asyncio
    async def test_duplicate_response_start_skips_header_injection(self):
        """A second http.response.start does not inject CORS headers again."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        original_send = AsyncMock()

        cors_send = mw._create_cors_send(original_send, "https://app.example.com", "/oauth2/token")

        first_message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
        await cors_send(first_message)

        # Reset so we can inspect the second call in isolation.
        original_send.reset_mock()

        second_message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
        await cors_send(second_message)

        # The second call should forward the message as-is (no header injection).
        original_send.assert_awaited_once()
        sent = original_send.await_args[0][0]
        header_names = [h[0] for h in sent.get("headers", [])]
        assert b"access-control-allow-origin" not in header_names


# ── _send_preflight_response ─────────────────────────────────────────────────


class TestSendPreflightResponse:
    @pytest.mark.asyncio
    async def test_allowed_origin_returns_200(self):
        """Preflight for an allowed origin sends 200 with CORS headers."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        mw._is_allowed_origin = AsyncMock(return_value=True)

        scope = _make_http_scope(
            path="/oauth2/token", method="OPTIONS", origin="https://app.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw._send_preflight_response(scope, receive, send, "https://app.example.com")

        assert send.await_count == 2

        start_msg = send.await_args_list[0][0][0]
        assert start_msg["status"] == 200

        header_dict = dict(start_msg["headers"])
        assert header_dict[b"access-control-allow-origin"] == b"https://app.example.com"
        assert header_dict[b"access-control-allow-methods"] == b"GET, POST, OPTIONS"
        assert (
            header_dict[b"access-control-allow-headers"]
            == b"Content-Type, Authorization, X-Requested-With"
        )
        assert header_dict[b"access-control-allow-credentials"] == b"true"
        assert header_dict[b"access-control-max-age"] == b"86400"
        assert header_dict[b"content-length"] == b"0"

        body_msg = send.await_args_list[1][0][0]
        assert body_msg["type"] == "http.response.body"
        assert body_msg["body"] == b""

    @pytest.mark.asyncio
    async def test_disallowed_origin_returns_403(self):
        """Preflight for a disallowed origin sends 403 with no headers."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        inner_app = AsyncMock()
        mw = OAuth2CORSMiddleware(inner_app)
        mw._is_allowed_origin = AsyncMock(return_value=False)

        scope = _make_http_scope(
            path="/oauth2/token", method="OPTIONS", origin="https://evil.example.com"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw._send_preflight_response(scope, receive, send, "https://evil.example.com")

        assert send.await_count == 2

        start_msg = send.await_args_list[0][0][0]
        assert start_msg["status"] == 403
        assert start_msg["headers"] == []

        body_msg = send.await_args_list[1][0][0]
        assert body_msg["type"] == "http.response.body"
        assert body_msg["body"] == b""


# ── _is_allowed_origin ───────────────────────────────────────────────────────


class TestIsAllowedOrigin:
    @pytest.mark.asyncio
    @patch("auth.core.database.async_session_factory", new_callable=MagicMock)
    async def test_found_in_allowed_origins(self, mock_factory):
        """Origin present in a client's allowed_origins returns True."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (
                ["https://app.example.com", "https://other.example.com"],
                ["https://app.example.com/callback"],
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        mw = OAuth2CORSMiddleware(AsyncMock())
        result = await mw._is_allowed_origin("https://app.example.com")

        assert result is True

    @pytest.mark.asyncio
    @patch("auth.core.database.async_session_factory", new_callable=MagicMock)
    async def test_found_in_redirect_uris_fallback(self, mock_factory):
        """Origin derived from redirect_uris when allowed_origins is empty/None."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mock_db = AsyncMock()
        mock_result = MagicMock()
        # allowed_origins is None/empty, so fallback to redirect_uris.
        mock_result.all.return_value = [
            (None, ["https://app.example.com/callback", "https://app.example.com/auth"]),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        mw = OAuth2CORSMiddleware(AsyncMock())
        result = await mw._is_allowed_origin("https://app.example.com")

        assert result is True

    @pytest.mark.asyncio
    @patch("auth.core.database.async_session_factory", new_callable=MagicMock)
    async def test_not_found_returns_false(self, mock_factory):
        """Origin that matches no client returns False."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (["https://other.example.com"], ["https://other.example.com/callback"]),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        mw = OAuth2CORSMiddleware(AsyncMock())
        result = await mw._is_allowed_origin("https://evil.example.com")

        assert result is False

    @pytest.mark.asyncio
    @patch("auth.core.database.async_session_factory", new_callable=MagicMock)
    async def test_db_exception_returns_false(self, mock_factory):
        """Database errors are caught and False is returned."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db unavailable"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_ctx

        mw = OAuth2CORSMiddleware(AsyncMock())
        result = await mw._is_allowed_origin("https://app.example.com")

        assert result is False


class TestCreateCorsSendOtherMessages:
    @pytest.mark.asyncio
    async def test_unknown_message_type_passes_through(self):
        """Messages that are neither response.start nor response.body are forwarded as-is."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mw = OAuth2CORSMiddleware(AsyncMock())
        original_send = AsyncMock()

        cors_send = mw._create_cors_send(original_send, "https://app.example.com", "/oauth2/token")

        trailers = {"type": "http.response.trailers", "headers": []}
        await cors_send(trailers)

        original_send.assert_awaited_once_with(trailers)


class TestIsAllowedOriginRedirectUriFallback:
    @pytest.mark.asyncio
    async def test_redirect_uri_origins_scanned_across_clients(self):
        """Clients without allowed_origins fall back to matching redirect_uri origins."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mw = OAuth2CORSMiddleware(AsyncMock())

        rows = [
            # No match: both redirect URIs point elsewhere.
            (None, ["https://other.example.com/cb", "https://nope.example.com/cb"]),
            # Match on the second redirect URI of the second client.
            ([], ["https://first.example.com/cb", "https://app.example.com/callback"]),
        ]

        with _patched_client_rows(rows):
            assert await mw._is_allowed_origin("https://app.example.com") is True

    @pytest.mark.asyncio
    async def test_no_client_matches_returns_false(self):
        """Exhausting every client's redirect URIs without a match denies the origin."""
        from auth.middlewares.cors import OAuth2CORSMiddleware

        mw = OAuth2CORSMiddleware(AsyncMock())

        rows = [
            (None, ["https://other.example.com/cb"]),
            ([], ["https://nope.example.com/cb", "https://nada.example.com/cb"]),
        ]

        with _patched_client_rows(rows):
            assert await mw._is_allowed_origin("https://app.example.com") is False


def _patched_client_rows(rows):
    """Patch the async session factory + client service to yield ``rows``."""
    db = AsyncMock()
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=db)
    session_ctx.__aexit__ = AsyncMock(return_value=False)

    service = MagicMock()
    service.list_active_cors_tuples = AsyncMock(return_value=rows)

    factory = patch("auth.core.database.async_session_factory", return_value=session_ctx)
    svc = patch("auth.services.oauth2_client.OAuth2ClientService", return_value=service)

    class _Ctx:
        def __enter__(self):
            factory.start()
            svc.start()
            return self

        def __exit__(self, *exc):
            svc.stop()
            factory.stop()
            return False

    return _Ctx()
