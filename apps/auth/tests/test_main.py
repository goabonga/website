# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.main — FastAPI application setup."""

from unittest.mock import MagicMock, patch

import pytest
from auth.config import settings
from fastapi import HTTPException, status

# ── _wants_html ─────────────────────────────────────────────────────────────


class TestWantsHtml:
    def test_html_accept(self):
        from auth.main import _wants_html

        request = MagicMock()
        request.headers.get.return_value = "text/html"
        assert _wants_html(request) is True

    def test_json_accept(self):
        from auth.main import _wants_html

        request = MagicMock()
        request.headers.get.return_value = "application/json"
        assert _wants_html(request) is False

    def test_both_prefers_json(self):
        from auth.main import _wants_html

        request = MagicMock()
        request.headers.get.return_value = "text/html, application/json"
        assert _wants_html(request) is False

    def test_empty_accept(self):
        from auth.main import _wants_html

        request = MagicMock()
        request.headers.get.return_value = ""
        assert _wants_html(request) is False

    def test_no_accept_header(self):
        from auth.main import _wants_html

        request = MagicMock()
        request.headers.get.return_value = ""
        assert _wants_html(request) is False


# ── http_exception_handler ──────────────────────────────────────────────────


class TestHttpExceptionHandler:
    @pytest.mark.asyncio
    async def test_403_html_renders_template(self):
        from auth.main import http_exception_handler

        request = MagicMock()
        request.headers.get.return_value = "text/html"
        exc = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        with patch("auth.main.templates") as mock_templates:
            mock_response = MagicMock()
            mock_templates.TemplateResponse.return_value = mock_response
            result = await http_exception_handler(request, exc)

        assert result is mock_response
        mock_templates.TemplateResponse.assert_called_once_with(
            request=request,
            name="errors/403.html",
            context={"detail": "Forbidden"},
            status_code=403,
            headers=None,
        )

    @pytest.mark.asyncio
    async def test_403_json_api(self):
        from auth.main import http_exception_handler

        request = MagicMock()
        request.headers.get.return_value = "application/json"
        exc = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        result = await http_exception_handler(request, exc)
        assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_headers_of_the_exception_are_sent(self):
        from auth.main import http_exception_handler

        request = MagicMock()
        request.headers.get.return_value = "text/html"
        exc = HTTPException(
            status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/auth/login?next=%2Fa"}
        )

        result = await http_exception_handler(request, exc)

        assert result.status_code == 303
        assert result.headers["location"] == "/auth/login?next=%2Fa"

    @pytest.mark.asyncio
    async def test_404_json(self):
        from auth.main import http_exception_handler

        request = MagicMock()
        request.headers.get.return_value = "text/html"
        exc = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

        # 404 is not 403, so always JSON
        result = await http_exception_handler(request, exc)
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_500_json(self):
        from auth.main import http_exception_handler

        request = MagicMock()
        request.headers.get.return_value = ""
        exc = HTTPException(status_code=500, detail="Internal Server Error")

        result = await http_exception_handler(request, exc)
        assert result.status_code == 500


# ── app instance ────────────────────────────────────────────────────────────


class TestAppInstance:
    def test_app_exists(self):
        from auth.main import app

        assert app is not None
        assert app.title == settings.app_title

    def test_swagger_client_comes_from_the_settings(self):
        from auth.main import swagger_init_oauth

        assert swagger_init_oauth["clientId"] == settings.swagger_client_id
        assert swagger_init_oauth["scopes"] == settings.swagger_scopes

    def test_docs_url(self):
        """Docs URL is None (custom /docs route serves Swagger UI)."""
        from auth.main import app

        assert app.docs_url is None

    def test_redoc_disabled(self):
        from auth.main import app

        assert app.redoc_url is None

    def test_has_router(self):
        from auth.main import app

        # Should have routes registered
        assert len(app.routes) > 0


# ── /docs and /docs/oauth2-redirect ─────────────────────────────────────────


class TestSwaggerRoutes:
    @pytest.mark.asyncio
    async def test_custom_swagger_ui_uses_local_assets(self):
        from auth.main import custom_swagger_ui

        with patch("auth.main.STATIC_DIR") as static_dir:
            static_dir.__truediv__ = lambda _self, name: _FakePath(True)
            response = await custom_swagger_ui()

        body = response.body.decode()
        assert "/static/swagger-ui-bundle.js" in body
        assert "/static/swagger-ui.css" in body

    @pytest.mark.asyncio
    async def test_custom_swagger_ui_falls_back_to_cdn(self):
        from auth.main import custom_swagger_ui

        with patch("auth.main.STATIC_DIR") as static_dir:
            static_dir.__truediv__ = lambda _self, name: _FakePath(False)
            response = await custom_swagger_ui()

        body = response.body.decode()
        assert "cdn.jsdelivr.net" in body

    @pytest.mark.asyncio
    async def test_swagger_ui_redirect(self):
        from auth.main import swagger_ui_redirect

        response = await swagger_ui_redirect()
        assert response.status_code == 200


class _FakePath:
    """Minimal stand-in for a pathlib.Path with a controlled ``exists()``."""

    def __init__(self, exists: bool):
        self._exists = exists

    def exists(self) -> bool:
        return self._exists


# ── module-level tenant middleware wiring ───────────────────────────────────


class TestTenantMiddlewareWiring:
    def test_tenant_middleware_absent_by_default(self):
        from auth.main import app

        names = [m.cls.__name__ for m in app.user_middleware]
        assert "TenantMiddleware" not in names
