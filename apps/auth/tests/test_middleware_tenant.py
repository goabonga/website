# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.middlewares.tenant — Tenant resolution middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.middlewares.tenant import (
    TenantContext,
    TenantMiddleware,
    get_csrf_cookie_name,
    get_session_cookie_domain,
    get_session_cookie_name,
    get_tenant_context,
    require_tenant,
    set_tenant_context,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_scope(host="example.com", path="/", query_string=b""):
    """Build a minimal ASGI HTTP scope dict."""
    return {
        "type": "http",
        "headers": [(b"host", host.encode("utf-8"))],
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string,
    }


def _make_db_mocks(row=None, side_effect=None):
    """Build mocked async_session_factory, session, and result.

    Args:
        row: The value returned by ``result.first()``.
        side_effect: An exception to raise on ``db.execute()``.

    Returns:
        A MagicMock that works as ``async_session_factory`` context manager.
    """
    mock_db = AsyncMock()
    if side_effect:
        mock_db.execute = AsyncMock(side_effect=side_effect)
    else:
        mock_result = MagicMock()
        mock_result.first.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_factory


# ── TenantContext dataclass ──────────────────────────────────────────────────


class TestTenantContext:
    def test_default_values(self):
        ctx = TenantContext()
        assert ctx.tenant_id is None
        assert ctx.tenant_slug is None
        assert ctx.resolution_method is None

    def test_custom_values(self):
        ctx = TenantContext(tenant_id="uuid-1", tenant_slug="acme", resolution_method="subdomain")
        assert ctx.tenant_id == "uuid-1"
        assert ctx.tenant_slug == "acme"
        assert ctx.resolution_method == "subdomain"


# ── get_tenant_context / set_tenant_context ──────────────────────────────────


class TestTenantContextVars:
    def test_get_default_none(self):
        set_tenant_context(None)
        assert get_tenant_context() is None

    def test_set_and_get(self):
        ctx = TenantContext(tenant_id="t1", tenant_slug="slug1", resolution_method="path")
        set_tenant_context(ctx)
        try:
            result = get_tenant_context()
            assert result is ctx
            assert result.tenant_id == "t1"
        finally:
            set_tenant_context(None)


# ── TenantMiddleware.__init__ ────────────────────────────────────────────────


class TestTenantMiddlewareInit:
    def test_stores_attributes(self):
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="Auth.Example.COM", custom_domain_lookup=False)
        assert mw.app is app
        assert mw.base_domain == "auth.example.com"
        assert mw.custom_domain_lookup is False

    def test_default_custom_domain_lookup(self):
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="example.com")
        assert mw.custom_domain_lookup is True


# ── TenantMiddleware.__call__ ────────────────────────────────────────────────


class TestTenantMiddlewareCall:
    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self):
        """Non-http scope types (websocket, lifespan) pass through unchanged."""
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="example.com")
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        app.assert_awaited_once_with(scope, receive, send)
        assert "tenant" not in scope

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_platform_tenant_on_subdomain_triggers_redirect(self, mock_resolve):
        """When platform tenant resolves on a subdomain host, redirect to base domain."""
        mock_resolve.return_value = TenantContext(
            tenant_id="plat-1", tenant_slug="platform", resolution_method="platform"
        )
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")
        scope = _make_http_scope(host="sub.auth.example.com", path="/dashboard")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        # Should have sent a 302 redirect
        assert send.await_count == 2
        start_call = send.await_args_list[0][0][0]
        assert start_call["type"] == "http.response.start"
        assert start_call["status"] == 302
        headers = dict(start_call["headers"])
        assert headers[b"location"] == b"https://auth.example.com/dashboard"
        # The inner app should NOT have been called
        app.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_platform_redirect_with_query_string(self, mock_resolve):
        """Redirect preserves query string."""
        mock_resolve.return_value = TenantContext(
            tenant_id="plat-1", tenant_slug="platform", resolution_method="platform"
        )
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")
        scope = _make_http_scope(
            host="sub.auth.example.com", path="/login", query_string=b"next=/home"
        )
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        start_call = send.await_args_list[0][0][0]
        headers = dict(start_call["headers"])
        assert headers[b"location"] == b"https://auth.example.com/login?next=/home"

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_normal_request_sets_and_clears_context(self, mock_resolve):
        """Normal request sets scope['tenant'] and context var, clears context after."""
        tenant = TenantContext(tenant_id="t-1", tenant_slug="acme", resolution_method="subdomain")
        mock_resolve.return_value = tenant

        captured_context = {}

        async def mock_app(scope, receive, send):
            captured_context["scope_tenant"] = scope.get("tenant")
            captured_context["ctx_var"] = get_tenant_context()

        mw = TenantMiddleware(mock_app, base_domain="auth.example.com")
        scope = _make_http_scope(host="auth.example.com", path="/")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        assert captured_context["scope_tenant"] is tenant
        assert captured_context["ctx_var"] is tenant
        # After the call, context var is cleared
        assert get_tenant_context() is None

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_context_cleared_even_on_exception(self, mock_resolve):
        """Context var is cleared even if the inner app raises."""
        mock_resolve.return_value = TenantContext(
            tenant_id="t-1", tenant_slug="acme", resolution_method="path"
        )

        async def failing_app(scope, receive, send):
            raise RuntimeError("boom")

        mw = TenantMiddleware(failing_app, base_domain="example.com")
        scope = _make_http_scope(host="example.com")
        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(RuntimeError, match="boom"):
            await mw(scope, receive, send)

        assert get_tenant_context() is None

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_platform_on_base_domain_no_redirect(self, mock_resolve):
        """Platform tenant on the base domain itself should NOT redirect."""
        mock_resolve.return_value = TenantContext(
            tenant_id="plat-1", tenant_slug="platform", resolution_method="platform"
        )
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")
        scope = _make_http_scope(host="auth.example.com", path="/")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        app.assert_awaited_once()


# ── _resolve_from_path ───────────────────────────────────────────────────────


class TestResolveFromPath:
    @pytest.mark.asyncio
    @patch(
        "auth.middlewares.tenant.TenantMiddleware._lookup_tenant_id_by_slug", new_callable=AsyncMock
    )
    async def test_valid_path_prefix(self, mock_lookup):
        """Path /t/<slug>/rest rewrites scope and returns context."""
        mock_lookup.return_value = "uuid-abc"
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="example.com")
        scope = _make_http_scope(path="/t/acme-corp/dashboard/settings")

        result = await mw._resolve_from_path("/t/acme-corp/dashboard/settings", scope)

        assert result is not None
        assert result.tenant_slug == "acme-corp"
        assert result.tenant_id == "uuid-abc"
        assert result.resolution_method == "path"
        # Scope should have been rewritten
        assert scope["path"] == "/dashboard/settings"
        assert scope["raw_path"] == b"/dashboard/settings"
        mock_lookup.assert_awaited_once_with("acme-corp")

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        """Paths not matching /t/<slug>/... return None."""
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="example.com")
        scope = _make_http_scope(path="/api/users")

        result = await mw._resolve_from_path("/api/users", scope)
        assert result is None


# ── _lookup_tenant_id_by_slug ────────────────────────────────────────────────


class TestLookupTenantIdBySlug:
    @pytest.mark.asyncio
    async def test_found(self):
        """Returns str(id) when tenant row is found."""
        factory = _make_db_mocks(row=MagicMock(id="uuid-42"))
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._lookup_tenant_id_by_slug("acme")
            assert result == "uuid-42"

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns None when no tenant row matches."""
        factory = _make_db_mocks(row=None)
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._lookup_tenant_id_by_slug("nonexistent")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self):
        """Returns None on database error."""
        factory = _make_db_mocks(side_effect=RuntimeError("DB down"))
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._lookup_tenant_id_by_slug("acme")
            assert result is None


# ── _resolve_from_subdomain ──────────────────────────────────────────────────


class TestResolveFromSubdomain:
    @pytest.mark.asyncio
    @patch(
        "auth.middlewares.tenant.TenantMiddleware._lookup_tenant_id_by_slug", new_callable=AsyncMock
    )
    async def test_valid_subdomain(self, mock_lookup):
        """Valid subdomain of base domain resolves tenant."""
        mock_lookup.return_value = "uuid-sub"
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")

        result = await mw._resolve_from_subdomain("acme.auth.example.com")

        assert result is not None
        assert result.tenant_slug == "acme"
        assert result.tenant_id == "uuid-sub"
        assert result.resolution_method == "subdomain"
        mock_lookup.assert_awaited_once_with("acme")

    @pytest.mark.asyncio
    async def test_not_a_subdomain(self):
        """Host not ending with base domain returns None."""
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")

        result = await mw._resolve_from_subdomain("other.domain.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_slug_format(self):
        """Subdomain with invalid characters returns None."""
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")

        # Uppercase not matching the pattern
        result = await mw._resolve_from_subdomain("INVALID.auth.example.com")
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "auth.middlewares.tenant.TenantMiddleware._lookup_tenant_id_by_slug", new_callable=AsyncMock
    )
    async def test_slug_not_found_in_db(self, mock_lookup):
        """Valid subdomain format but no matching tenant returns None."""
        mock_lookup.return_value = None
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")

        result = await mw._resolve_from_subdomain("unknown.auth.example.com")
        assert result is None


# ── _resolve_from_custom_domain ──────────────────────────────────────────────


class TestResolveFromCustomDomain:
    @pytest.mark.asyncio
    async def test_found(self):
        """Returns context when custom domain matches a tenant."""
        row = MagicMock(id="uuid-cd", slug="custom-tenant")
        factory = _make_db_mocks(row=row)
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="auth.example.com")
            result = await mw._resolve_from_custom_domain("app.custom.com")

            assert result is not None
            assert result.tenant_id == "uuid-cd"
            assert result.tenant_slug == "custom-tenant"
            assert result.resolution_method == "custom_domain"

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns None when no custom domain matches."""
        factory = _make_db_mocks(row=None)
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="auth.example.com")
            result = await mw._resolve_from_custom_domain("unknown.com")
            assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self):
        """Returns None on database error."""
        factory = _make_db_mocks(side_effect=RuntimeError("connection refused"))
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="auth.example.com")
            result = await mw._resolve_from_custom_domain("broken.com")
            assert result is None


# ── _send_redirect ───────────────────────────────────────────────────────────


class TestSendRedirect:
    @pytest.mark.asyncio
    async def test_sends_302(self):
        """Sends a 302 redirect with the correct location header."""
        send = AsyncMock()

        await TenantMiddleware._send_redirect(send, "https://auth.example.com/target")

        assert send.await_count == 2
        start_msg = send.await_args_list[0][0][0]
        body_msg = send.await_args_list[1][0][0]

        assert start_msg["type"] == "http.response.start"
        assert start_msg["status"] == 302
        headers = dict(start_msg["headers"])
        assert headers[b"location"] == b"https://auth.example.com/target"
        assert headers[b"content-length"] == b"0"

        assert body_msg["type"] == "http.response.body"
        assert body_msg["body"] == b""


# ── _resolve_platform_tenant ─────────────────────────────────────────────────


class TestResolvePlatformTenant:
    @pytest.mark.asyncio
    async def test_found(self):
        """Returns context when a platform tenant exists."""
        row = MagicMock(id="uuid-plat", slug="platform")
        factory = _make_db_mocks(row=row)
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._resolve_platform_tenant()

            assert result is not None
            assert result.tenant_id == "uuid-plat"
            assert result.tenant_slug == "platform"
            assert result.resolution_method == "platform"

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns None when no platform tenant exists."""
        factory = _make_db_mocks(row=None)
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._resolve_platform_tenant()
            assert result is None

    @pytest.mark.asyncio
    async def test_db_error(self):
        """Returns None on database error."""
        factory = _make_db_mocks(side_effect=RuntimeError("timeout"))
        with patch("auth.core.database.async_session_factory", factory):
            app = AsyncMock()
            mw = TenantMiddleware(app, base_domain="example.com")
            result = await mw._resolve_platform_tenant()
            assert result is None


# ── get_session_cookie_name ──────────────────────────────────────────────────


class TestGetSessionCookieName:
    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_with_subdomain_tenant(self, mock_settings, mock_get_ctx):
        """Subdomain tenant gets a scoped cookie name."""
        mock_settings.session_cookie_name = "session"
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="subdomain"
        )
        result = get_session_cookie_name()
        assert result == "session_acme"

    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_with_path_tenant(self, mock_settings, mock_get_ctx):
        """Path-resolved tenant gets a scoped cookie name."""
        mock_settings.session_cookie_name = "session"
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t2", tenant_slug="beta", resolution_method="path"
        )
        result = get_session_cookie_name()
        assert result == "session_beta"

    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_without_tenant(self, mock_settings, mock_get_ctx):
        """No tenant context returns the default cookie name."""
        mock_settings.session_cookie_name = "session"
        mock_get_ctx.return_value = None
        result = get_session_cookie_name()
        assert result == "session"

    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_custom_domain_tenant_returns_default(self, mock_settings, mock_get_ctx):
        """Custom domain resolution does not scope the cookie name."""
        mock_settings.session_cookie_name = "session"
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t3", tenant_slug="gamma", resolution_method="custom_domain"
        )
        result = get_session_cookie_name()
        assert result == "session"


# ── get_csrf_cookie_name ─────────────────────────────────────────────────────


class TestGetCsrfCookieName:
    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_with_tenant(self, mock_get_ctx):
        """Subdomain/path tenant gets a scoped CSRF cookie name."""
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="subdomain"
        )
        result = get_csrf_cookie_name()
        assert result == "csrf_acme"

    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_with_path_tenant(self, mock_get_ctx):
        """Path tenant gets a scoped CSRF cookie name."""
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="beta", resolution_method="path"
        )
        result = get_csrf_cookie_name()
        assert result == "csrf_beta"

    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_without_tenant(self, mock_get_ctx):
        """No tenant context returns the default CSRF cookie name."""
        mock_get_ctx.return_value = None
        result = get_csrf_cookie_name()
        assert result == "csrf_token"

    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_custom_domain_returns_default(self, mock_get_ctx):
        """Custom domain resolution returns the default CSRF cookie name."""
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t3", tenant_slug="gamma", resolution_method="custom_domain"
        )
        result = get_csrf_cookie_name()
        assert result == "csrf_token"


# ── get_session_cookie_domain ────────────────────────────────────────────────


class TestGetSessionCookieDomain:
    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_subdomain_with_base_domain(self, mock_settings, mock_get_ctx):
        """Subdomain tenant with configured base domain returns dotted domain."""
        mock_settings.tenant_base_domain = "auth.example.com"
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="subdomain"
        )
        result = get_session_cookie_domain()
        assert result == ".auth.example.com"

    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_path_with_base_domain(self, mock_settings, mock_get_ctx):
        """Path tenant with configured base domain returns dotted domain."""
        mock_settings.tenant_base_domain = "auth.example.com"
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="path"
        )
        result = get_session_cookie_domain()
        assert result == ".auth.example.com"

    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_no_tenant(self, mock_get_ctx):
        """No tenant context returns None."""
        mock_get_ctx.return_value = None
        result = get_session_cookie_domain()
        assert result is None

    @patch("auth.middlewares.tenant.get_tenant_context")
    @patch("auth.config.settings")
    def test_no_base_domain_configured(self, mock_settings, mock_get_ctx):
        """Subdomain tenant with empty base domain returns None."""
        mock_settings.tenant_base_domain = ""
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="subdomain"
        )
        result = get_session_cookie_domain()
        assert result is None

    @patch("auth.middlewares.tenant.get_tenant_context")
    def test_custom_domain_returns_none(self, mock_get_ctx):
        """Custom domain resolution returns None."""
        mock_get_ctx.return_value = TenantContext(
            tenant_id="t1", tenant_slug="acme", resolution_method="custom_domain"
        )
        result = get_session_cookie_domain()
        assert result is None


# ── require_tenant ───────────────────────────────────────────────────────────


class TestRequireTenant:
    def test_with_context(self):
        """Returns context when available."""
        ctx = TenantContext(tenant_id="t1", tenant_slug="acme", resolution_method="path")
        set_tenant_context(ctx)
        try:
            result = require_tenant()
            assert result is ctx
        finally:
            set_tenant_context(None)

    def test_no_context_raises(self):
        """Raises ValueError when no context is set."""
        set_tenant_context(None)
        with pytest.raises(ValueError, match="No tenant context available"):
            require_tenant()

    def test_context_with_none_slug_raises(self):
        """Raises ValueError when context has no slug."""
        ctx = TenantContext(tenant_id="t1", tenant_slug=None, resolution_method="platform")
        set_tenant_context(ctx)
        try:
            with pytest.raises(ValueError, match="No tenant context available"):
                require_tenant()
        finally:
            set_tenant_context(None)


# ---------------------------------------------------------------------------
# _resolve_tenant — full resolution chain (not mocked)
# ---------------------------------------------------------------------------


class TestResolveTenantChain:
    """Exercises the real _resolve_tenant ordering: path → subdomain → custom → platform."""

    def _middleware(self, custom_domain_lookup=True):
        return TenantMiddleware(
            AsyncMock(), base_domain="example.com", custom_domain_lookup=custom_domain_lookup
        )

    @pytest.mark.asyncio
    async def test_path_prefix_wins(self):
        mw = self._middleware()
        ctx = TenantContext(tenant_id="t1", tenant_slug="acme", resolution_method="path")
        scope = _make_http_scope(host="example.com:8000", path="/t/acme/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=ctx)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock()) as sub,
        ):
            result = await mw._resolve_tenant(scope)

        assert result is ctx
        sub.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_subdomain_used_when_path_misses(self):
        mw = self._middleware()
        ctx = TenantContext(tenant_id="t1", tenant_slug="acme", resolution_method="subdomain")
        scope = _make_http_scope(host="acme.example.com", path="/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=ctx)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock()) as custom,
        ):
            result = await mw._resolve_tenant(scope)

        assert result is ctx
        custom.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_domain_used_when_subdomain_misses(self):
        mw = self._middleware()
        ctx = TenantContext(tenant_id="t1", tenant_slug="acme", resolution_method="custom_domain")
        scope = _make_http_scope(host="login.acme.io", path="/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock(return_value=ctx)),
        ):
            result = await mw._resolve_tenant(scope)

        assert result is ctx

    @pytest.mark.asyncio
    async def test_custom_domain_miss_falls_back_to_platform(self):
        mw = self._middleware()
        platform = TenantContext(tenant_id="p", tenant_slug=None, resolution_method="platform")
        scope = _make_http_scope(host="login.acme.io", path="/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_platform_tenant", AsyncMock(return_value=platform)),
        ):
            result = await mw._resolve_tenant(scope)

        assert result is platform

    @pytest.mark.asyncio
    async def test_custom_domain_skipped_when_lookup_disabled(self):
        mw = self._middleware(custom_domain_lookup=False)
        platform = TenantContext(tenant_id="p", tenant_slug=None, resolution_method="platform")
        scope = _make_http_scope(host="login.acme.io", path="/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock()) as custom,
            patch.object(mw, "_resolve_platform_tenant", AsyncMock(return_value=platform)),
        ):
            result = await mw._resolve_tenant(scope)

        assert result is platform
        custom.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_domain_skipped_on_base_domain(self):
        mw = self._middleware()
        platform = TenantContext(tenant_id="p", tenant_slug=None, resolution_method="platform")
        scope = _make_http_scope(host="example.com", path="/login")

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock()) as custom,
            patch.object(mw, "_resolve_platform_tenant", AsyncMock(return_value=platform)),
        ):
            result = await mw._resolve_tenant(scope)

        assert result is platform
        custom.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_custom_domain_skipped_when_host_missing(self):
        mw = self._middleware()
        platform = TenantContext(tenant_id="p", tenant_slug=None, resolution_method="platform")
        scope = {"type": "http", "headers": [], "path": "/login", "query_string": b""}

        with (
            patch.object(mw, "_resolve_from_path", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_subdomain", AsyncMock(return_value=None)),
            patch.object(mw, "_resolve_from_custom_domain", AsyncMock()) as custom,
            patch.object(mw, "_resolve_platform_tenant", AsyncMock(return_value=platform)),
        ):
            result = await mw._resolve_tenant(scope)

        assert result is platform
        custom.assert_not_awaited()


class TestCallHostPortStripping:
    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.TenantMiddleware._resolve_tenant")
    async def test_port_is_stripped_before_subdomain_redirect_check(self, mock_resolve):
        """A ``host`` header carrying a port still matches the base domain suffix."""
        mock_resolve.return_value = TenantContext(
            tenant_id="plat-1", tenant_slug="platform", resolution_method="platform"
        )
        app = AsyncMock()
        mw = TenantMiddleware(app, base_domain="auth.example.com")
        scope = _make_http_scope(host="sub.auth.example.com:8000", path="/dashboard")

        await mw(scope, AsyncMock(), (send := AsyncMock()))

        start_call = send.await_args_list[0][0][0]
        assert start_call["status"] == 302
        headers = dict(start_call["headers"])
        assert headers[b"location"] == b"https://auth.example.com/dashboard"
        app.assert_not_awaited()
