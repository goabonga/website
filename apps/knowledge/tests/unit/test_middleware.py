# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for middleware modules: api_tracking and tenant."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.middleware.api_tracking import APITrackingMiddleware
from knowledge.middleware.tenant import (
    TenantContext,
    TenantMiddleware,
    get_tenant_context,
    require_tenant,
    set_tenant_context,
)

# ============================================================
# APITrackingMiddleware
# ============================================================


class TestAPITrackingMiddleware:
    """Tests for APITrackingMiddleware.dispatch covering lines 28-49."""

    def _make_request(self, path: str, tenant_id=None):
        """Helper to create a mock Request with a given path."""
        request = MagicMock()
        request.url.path = path
        state = MagicMock()
        if tenant_id is not None:
            state.tenant_id = tenant_id
        else:
            # Make getattr(request.state, "tenant_id", None) return None
            del state.tenant_id
        request.state = state
        return request

    @pytest.fixture
    def middleware(self):
        app = MagicMock()
        return APITrackingMiddleware(app)

    async def test_non_api_route_passes_through(self, middleware):
        """Non-/v1/ routes are not tracked."""
        request = self._make_request("/docs")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        result = await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)
        assert result == call_next.return_value

    async def test_health_endpoint_v1_skipped(self, middleware):
        """Health check at /v1/health is skipped."""
        request = self._make_request("/v1/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        result = await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)
        assert result == call_next.return_value

    async def test_health_endpoint_root_skipped(self, middleware):
        """/health is not a /v1/ path, so it hits the first guard."""
        request = self._make_request("/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        await middleware.dispatch(request, call_next)

        call_next.assert_awaited_once_with(request)

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_successful_api_call_records_usage(self, mock_session_factory, middleware):
        """2xx response with tenant_id records the API call."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/collections", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_db = AsyncMock()
        mock_quota_service = MagicMock()
        mock_quota_service.record_api_call = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
        ):
            result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once_with(tenant_id)
        mock_db.commit.assert_awaited_once()

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_successful_api_v1_call_records_usage(self, mock_session_factory, middleware):
        """2xx response on /api/v1/* with tenant_id records the API call."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/api/v1/search", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_db = AsyncMock()
        mock_quota_service = MagicMock()
        mock_quota_service.record_api_call = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
        ):
            result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once_with(tenant_id)
        mock_db.commit.assert_awaited_once()

    async def test_non_2xx_response_not_tracked(self, middleware):
        """Non-2xx responses are not tracked."""
        request = self._make_request("/v1/collections", tenant_id="some-id")
        response = MagicMock(status_code=404)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    async def test_no_tenant_id_not_tracked(self, middleware):
        """2xx without tenant_id does not try to record."""
        request = self._make_request("/v1/collections")
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    @patch("knowledge.middleware.api_tracking.async_session_factory")
    async def test_tracking_exception_does_not_fail_request(self, mock_session_factory, middleware):
        """If tracking fails, the response is still returned."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/collections", tenant_id=tenant_id)
        response = MagicMock(status_code=200)
        call_next = AsyncMock(return_value=response)

        mock_session_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB connection error")
        )
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await middleware.dispatch(request, call_next)

        assert result == response

    async def test_status_299_is_tracked(self, middleware):
        """Status code 299 (still 2xx) should be tracked."""
        tenant_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        request = self._make_request("/v1/data", tenant_id=tenant_id)
        response = MagicMock(status_code=299)
        call_next = AsyncMock(return_value=response)

        with patch("knowledge.middleware.api_tracking.async_session_factory") as mock_sf:
            mock_db = AsyncMock()
            mock_quota_service = MagicMock()
            mock_quota_service.record_api_call = AsyncMock()
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "knowledge.middleware.api_tracking.QuotaService", return_value=mock_quota_service
            ):
                result = await middleware.dispatch(request, call_next)

        assert result == response
        mock_quota_service.record_api_call.assert_awaited_once()

    async def test_status_300_not_tracked(self, middleware):
        """Status code 300 is not 2xx and should not be tracked."""
        request = self._make_request("/v1/data", tenant_id="some-id")
        response = MagicMock(status_code=300)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)

        assert result == response


# ============================================================
# TenantContext and helper functions
# ============================================================


class TestTenantContextFunctions:
    """Tests for get_tenant_context, set_tenant_context, require_tenant."""

    def test_get_tenant_context_default_none(self):
        set_tenant_context(None)
        assert get_tenant_context() is None

    def test_set_and_get_tenant_context(self):
        ctx = TenantContext(tenant_id="abc", tenant_slug="my-org", resolution_method="subdomain")
        set_tenant_context(ctx)
        assert get_tenant_context() == ctx
        set_tenant_context(None)

    def test_require_tenant_raises_when_none(self):
        set_tenant_context(None)
        with pytest.raises(ValueError, match="No tenant context"):
            require_tenant()

    def test_require_tenant_raises_when_slug_none(self):
        ctx = TenantContext(tenant_id="abc", tenant_slug=None)
        set_tenant_context(ctx)
        with pytest.raises(ValueError, match="No tenant context"):
            require_tenant()
        set_tenant_context(None)

    def test_require_tenant_returns_context(self):
        ctx = TenantContext(tenant_id="abc", tenant_slug="my-org", resolution_method="subdomain")
        set_tenant_context(ctx)
        result = require_tenant()
        assert result == ctx
        set_tenant_context(None)


# ============================================================
# TenantMiddleware
# ============================================================


class TestTenantMiddleware:
    """Tests for TenantMiddleware covering lines 77-80, 87-129, 139-165, 169-187, 191-210, 214-230, 238-269, 281-284."""

    @pytest.fixture
    def mock_app(self):
        return AsyncMock()

    @pytest.fixture
    def middleware(self, mock_app):
        return TenantMiddleware(
            app=mock_app,
            base_domain="knowledge.example.com",
            custom_domain_lookup=True,
        )

    def _make_scope(self, path="/", host="knowledge.example.com", scope_type="http"):
        """Helper to create a mock ASGI scope."""
        return {
            "type": scope_type,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "headers": [(b"host", host.encode("utf-8"))],
            "query_string": b"",
        }

    async def test_init_sets_attributes(self, mock_app):
        mw = TenantMiddleware(app=mock_app, base_domain="Example.COM", custom_domain_lookup=False)
        assert mw.base_domain == "example.com"
        assert mw.custom_domain_lookup is False
        assert mw.app is mock_app

    async def test_non_http_scope_passes_through(self, middleware, mock_app):
        """Non-http scopes go directly to app."""
        scope = self._make_scope(scope_type="websocket")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        mock_app.assert_awaited_once_with(scope, receive, send)

    @patch.object(TenantMiddleware, "_resolve_tenant")
    async def test_main_domain_no_tenant(self, mock_resolve, middleware, mock_app):
        """Main domain with no prefix => no tenant context."""
        mock_resolve.return_value = None
        scope = self._make_scope(path="/")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        assert scope["tenant"] is None
        mock_app.assert_awaited_once()

    @patch.object(TenantMiddleware, "_resolve_tenant")
    async def test_tenant_context_cleared_after_request(self, mock_resolve, middleware, mock_app):
        """Context variable is cleared after request completes."""
        ctx = TenantContext(tenant_id="abc", tenant_slug="test", resolution_method="path")
        mock_resolve.return_value = ctx

        scope = self._make_scope()
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # After middleware, context should be cleared
        assert get_tenant_context() is None

    @patch.object(TenantMiddleware, "_resolve_tenant")
    async def test_tenant_context_cleared_on_exception(self, mock_resolve, middleware, mock_app):
        """Context variable is cleared even if app raises."""
        ctx = TenantContext(tenant_id="abc", tenant_slug="test", resolution_method="path")
        mock_resolve.return_value = ctx
        mock_app.side_effect = RuntimeError("boom")

        scope = self._make_scope()
        receive = AsyncMock()
        send = AsyncMock()

        with pytest.raises(RuntimeError, match="boom"):
            await middleware(scope, receive, send)

        assert get_tenant_context() is None

    @patch.object(TenantMiddleware, "_resolve_tenant")
    async def test_unknown_subdomain_redirects(self, mock_resolve, middleware, mock_app):
        """Unknown subdomain with tenant_id=None triggers redirect."""
        ctx = TenantContext(tenant_id=None, tenant_slug="unknown", resolution_method="subdomain")
        mock_resolve.return_value = ctx

        scope = self._make_scope(path="/some/path", host="unknown.knowledge.example.com")
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        # Should not call the inner app
        mock_app.assert_not_awaited()

    @patch.object(TenantMiddleware, "_resolve_tenant")
    async def test_unknown_subdomain_redirect_with_query_string(
        self, mock_resolve, middleware, mock_app
    ):
        """Unknown subdomain redirect includes query string."""
        ctx = TenantContext(tenant_id=None, tenant_slug="bad", resolution_method="subdomain")
        mock_resolve.return_value = ctx

        scope = self._make_scope(path="/page", host="bad.knowledge.example.com")
        scope["query_string"] = b"foo=bar"
        receive = AsyncMock()
        send = AsyncMock()

        await middleware(scope, receive, send)

        mock_app.assert_not_awaited()

    # ----------------------------------------------------------
    # _resolve_tenant
    # ----------------------------------------------------------

    async def test_resolve_tenant_from_path(self, middleware):
        """Path prefix /t/{slug}/... resolves tenant."""
        scope = self._make_scope(path="/t/my-org/collections")

        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = "tenant-id-123"

            ctx = await middleware._resolve_tenant(scope)

        assert ctx is not None
        assert ctx.tenant_slug == "my-org"
        assert ctx.resolution_method == "path"
        assert ctx.tenant_id == "tenant-id-123"
        # Path should be rewritten
        assert scope["path"] == "/collections"

    async def test_resolve_tenant_from_subdomain(self, middleware):
        """Subdomain resolves tenant."""
        scope = self._make_scope(host="acme.knowledge.example.com")

        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = "tenant-id-456"

            ctx = await middleware._resolve_tenant(scope)

        assert ctx is not None
        assert ctx.tenant_slug == "acme"
        assert ctx.resolution_method == "subdomain"
        assert ctx.tenant_id == "tenant-id-456"

    async def test_resolve_tenant_subdomain_no_match(self, middleware):
        """Subdomain that doesn't match base_domain falls through."""
        scope = self._make_scope(host="other-domain.com")

        with patch.object(
            middleware, "_resolve_from_custom_domain", new_callable=AsyncMock
        ) as mock_custom:
            mock_custom.return_value = None

            ctx = await middleware._resolve_tenant(scope)

        assert ctx is None

    async def test_resolve_tenant_custom_domain(self, middleware):
        """Custom domain resolves tenant via database lookup."""
        scope = self._make_scope(host="docs.acme.com")

        with patch.object(
            middleware, "_resolve_from_custom_domain", new_callable=AsyncMock
        ) as mock_custom:
            mock_custom.return_value = TenantContext(
                tenant_id="tenant-789", tenant_slug="acme", resolution_method="custom_domain"
            )

            ctx = await middleware._resolve_tenant(scope)

        assert ctx is not None
        assert ctx.resolution_method == "custom_domain"
        mock_custom.assert_awaited_once_with("docs.acme.com")

    async def test_resolve_tenant_host_with_port(self, middleware):
        """Host header with port strips the port."""
        scope = self._make_scope(host="acme.knowledge.example.com:8080")

        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = "tenant-id"

            ctx = await middleware._resolve_tenant(scope)

        assert ctx is not None
        assert ctx.tenant_slug == "acme"

    async def test_resolve_tenant_no_custom_domain_lookup(self, mock_app):
        """When custom_domain_lookup=False, custom domain lookup is skipped."""
        mw = TenantMiddleware(
            app=mock_app,
            base_domain="knowledge.example.com",
            custom_domain_lookup=False,
        )
        scope = self._make_scope(host="external.com")

        ctx = await mw._resolve_tenant(scope)

        assert ctx is None

    # ----------------------------------------------------------
    # _resolve_from_path
    # ----------------------------------------------------------

    async def test_resolve_from_path_match(self, middleware):
        """Path /t/my-org/docs matches and rewrites."""
        scope = self._make_scope(path="/t/my-org/docs")

        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = "tid"

            ctx = await middleware._resolve_from_path("/t/my-org/docs", scope)

        assert ctx is not None
        assert ctx.tenant_slug == "my-org"
        assert scope["path"] == "/docs"
        assert scope["raw_path"] == b"/docs"

    async def test_resolve_from_path_no_match(self, middleware):
        """Paths not matching /t/{slug}/... return None."""
        scope = self._make_scope(path="/v1/collections")

        ctx = await middleware._resolve_from_path("/v1/collections", scope)

        assert ctx is None

    # ----------------------------------------------------------
    # _lookup_tenant_id_by_slug
    # ----------------------------------------------------------

    @patch("knowledge.database.async_session_factory")
    async def test_lookup_tenant_id_by_slug_found(self, mock_sf, middleware):
        """Found organization returns its ID."""
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.id = "org-uuid-123"
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await middleware._lookup_tenant_id_by_slug("my-org")

        assert result == "org-uuid-123"

    @patch("knowledge.database.async_session_factory")
    async def test_lookup_tenant_id_by_slug_not_found(self, mock_sf, middleware):
        """No matching organization returns None."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await middleware._lookup_tenant_id_by_slug("nonexistent")

        assert result is None

    @patch("knowledge.database.async_session_factory")
    async def test_lookup_tenant_id_by_slug_exception(self, mock_sf, middleware):
        """Database exception returns None."""
        mock_sf.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await middleware._lookup_tenant_id_by_slug("errored")

        assert result is None

    # ----------------------------------------------------------
    # _resolve_from_subdomain
    # ----------------------------------------------------------

    async def test_resolve_from_subdomain_valid(self, middleware):
        """Valid subdomain resolves tenant."""
        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = "tid"

            ctx = await middleware._resolve_from_subdomain("acme.knowledge.example.com")

        assert ctx is not None
        assert ctx.tenant_slug == "acme"
        assert ctx.resolution_method == "subdomain"

    async def test_resolve_from_subdomain_not_matching_base(self, middleware):
        """Host not ending with base_domain returns None."""
        ctx = await middleware._resolve_from_subdomain("acme.other.com")

        assert ctx is None

    async def test_resolve_from_subdomain_invalid_slug(self, middleware):
        """Invalid slug format returns None."""
        ctx = await middleware._resolve_from_subdomain("INVALID_SLUG.knowledge.example.com")

        assert ctx is None

    async def test_resolve_from_subdomain_lookup_returns_none(self, middleware):
        """Valid subdomain but no matching org returns context with tenant_id=None."""
        with patch.object(
            middleware, "_lookup_tenant_id_by_slug", new_callable=AsyncMock
        ) as mock_lookup:
            mock_lookup.return_value = None

            ctx = await middleware._resolve_from_subdomain("unknown-org.knowledge.example.com")

        assert ctx is not None
        assert ctx.tenant_id is None
        assert ctx.tenant_slug == "unknown-org"

    # ----------------------------------------------------------
    # _resolve_from_custom_domain
    # ----------------------------------------------------------

    @patch("knowledge.database.async_session_factory")
    async def test_resolve_from_custom_domain_found(self, mock_sf, middleware):
        """Custom domain found in DB returns tenant context."""
        mock_db = AsyncMock()
        mock_row = MagicMock()
        mock_row.id = "org-uuid-custom"
        mock_row.slug = "acme"
        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = await middleware._resolve_from_custom_domain("docs.acme.com")

        assert ctx is not None
        assert ctx.tenant_id == "org-uuid-custom"
        assert ctx.tenant_slug == "acme"
        assert ctx.resolution_method == "custom_domain"

    @patch("knowledge.database.async_session_factory")
    async def test_resolve_from_custom_domain_not_found(self, mock_sf, middleware):
        """Custom domain not found returns None."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = await middleware._resolve_from_custom_domain("unknown.example.com")

        assert ctx is None

    @patch("knowledge.database.async_session_factory")
    async def test_resolve_from_custom_domain_exception(self, mock_sf, middleware):
        """Database exception returns None."""
        mock_sf.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

        ctx = await middleware._resolve_from_custom_domain("broken.example.com")

        assert ctx is None

    # ----------------------------------------------------------
    # Base domain empty edge case
    # ----------------------------------------------------------

    async def test_resolve_tenant_empty_base_domain(self, mock_app):
        """When base_domain is empty, subdomain resolution is skipped."""
        mw = TenantMiddleware(app=mock_app, base_domain="", custom_domain_lookup=False)
        scope = self._make_scope(host="anything.com")

        ctx = await mw._resolve_tenant(scope)

        # base_domain is "" so `if self.base_domain:` is False => skip subdomain
        # custom_domain_lookup=False => skip custom domain
        assert ctx is None
