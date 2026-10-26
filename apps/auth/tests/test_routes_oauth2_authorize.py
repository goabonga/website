# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.authorize -- OAuth2 authorization endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from tests.conftest import make_oauth2_client, make_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.authorize"


def _mock_request(
    cookies=None,
    headers=None,
    url_path="/oauth2/authorize",
    url_query="",
    base_url="https://auth.example.com/",
):
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: (headers or {}).get(k, d))
    request.client = MagicMock()
    request.client.host = "10.0.0.1"
    request.url = MagicMock()
    request.url.scheme = "https"
    request.url.netloc = "auth.example.com"
    request.url.path = url_path
    request.url.query = url_query
    request.base_url = base_url
    return request


# ---------------------------------------------------------------------------
# get_tenant_prefix
# ---------------------------------------------------------------------------


class TestGetTenantPrefix:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.oauth2.authorize import get_tenant_prefix

        assert get_tenant_prefix() == ""

    @patch(f"{MODULE}.get_tenant_context")
    def test_path_resolution(self, mock_ctx):
        from auth.api.routes.oauth2.authorize import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "knowledge"
        ctx.resolution_method = "path"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == "/t/knowledge"

    @patch(f"{MODULE}.get_tenant_context")
    def test_subdomain_resolution(self, mock_ctx):
        from auth.api.routes.oauth2.authorize import get_tenant_prefix

        ctx = MagicMock()
        ctx.tenant_slug = "knowledge"
        ctx.resolution_method = "subdomain"
        mock_ctx.return_value = ctx
        assert get_tenant_prefix() == ""


# ---------------------------------------------------------------------------
# get_current_tenant_id
# ---------------------------------------------------------------------------


class TestGetCurrentTenantId:
    @patch(f"{MODULE}.get_tenant_context", return_value=None)
    def test_no_context(self, _):
        from auth.api.routes.oauth2.authorize import get_current_tenant_id

        assert get_current_tenant_id() is None

    @patch(f"{MODULE}.get_tenant_context")
    def test_with_context(self, mock_ctx):
        from auth.api.routes.oauth2.authorize import get_current_tenant_id

        ctx = MagicMock()
        ctx.tenant_id = "t-123"
        mock_ctx.return_value = ctx
        assert get_current_tenant_id() == "t-123"


# ---------------------------------------------------------------------------
# _build_error_redirect
# ---------------------------------------------------------------------------


class TestBuildErrorRedirect:
    def test_basic(self):
        from auth.api.routes.oauth2.authorize import _build_error_redirect

        result = _build_error_redirect("https://app.example.com/cb", "invalid_request")
        assert "error=invalid_request" in result
        assert result.startswith("https://app.example.com/cb?")

    def test_with_description_and_state(self):
        from auth.api.routes.oauth2.authorize import _build_error_redirect

        result = _build_error_redirect(
            "https://app.example.com/cb",
            "invalid_scope",
            error_description="Bad scope",
            state="xyz",
        )
        assert "error=invalid_scope" in result
        assert "error_description=Bad+scope" in result
        assert "state=xyz" in result

    def test_appends_with_ampersand_if_query_exists(self):
        from auth.api.routes.oauth2.authorize import _build_error_redirect

        result = _build_error_redirect("https://app.example.com/cb?foo=bar", "access_denied")
        assert "foo=bar&error=access_denied" in result

    def test_no_description_or_state(self):
        from auth.api.routes.oauth2.authorize import _build_error_redirect

        result = _build_error_redirect("https://app.example.com/cb", "server_error")
        assert "error_description" not in result
        assert "state" not in result


# ---------------------------------------------------------------------------
# _build_success_redirect
# ---------------------------------------------------------------------------


class TestBuildSuccessRedirect:
    def test_basic(self):
        from auth.api.routes.oauth2.authorize import _build_success_redirect

        result = _build_success_redirect("https://app.example.com/cb", "auth_code_123")
        assert "code=auth_code_123" in result
        assert result.startswith("https://app.example.com/cb?")

    def test_with_state(self):
        from auth.api.routes.oauth2.authorize import _build_success_redirect

        result = _build_success_redirect("https://app.example.com/cb", "code123", state="state_abc")
        assert "code=code123" in result
        assert "state=state_abc" in result

    def test_appends_with_ampersand(self):
        from auth.api.routes.oauth2.authorize import _build_success_redirect

        result = _build_success_redirect("https://app.example.com/cb?existing=1", "code1")
        assert "existing=1&code=code1" in result


# ---------------------------------------------------------------------------
# _parse_scopes
# ---------------------------------------------------------------------------


class TestParseScopes:
    def test_none_returns_openid(self):
        from auth.api.routes.oauth2.authorize import _parse_scopes

        assert _parse_scopes(None) == ["openid"]

    def test_empty_returns_openid(self):
        from auth.api.routes.oauth2.authorize import _parse_scopes

        assert _parse_scopes("") == ["openid"]

    def test_single_scope(self):
        from auth.api.routes.oauth2.authorize import _parse_scopes

        assert _parse_scopes("profile") == ["profile"]

    def test_multiple_scopes(self):
        from auth.api.routes.oauth2.authorize import _parse_scopes

        assert _parse_scopes("openid profile email") == ["openid", "profile", "email"]


# ---------------------------------------------------------------------------
# _is_valid_redirect_uri
# ---------------------------------------------------------------------------


class TestIsValidRedirectUri:
    def test_https_valid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("https://example.com/callback") is True

    def test_http_localhost_valid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("http://localhost/callback") is True
        assert _is_valid_redirect_uri("http://localhost:8080/callback") is True
        assert _is_valid_redirect_uri("http://127.0.0.1/callback") is True
        assert _is_valid_redirect_uri("http://127.0.0.1:3000/callback") is True

    def test_http_non_localhost_invalid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("http://example.com/callback") is False

    def test_custom_scheme_valid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("vpnclient://callback") is True
        assert _is_valid_redirect_uri("myapp://auth/callback") is True

    def test_no_scheme_invalid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("/callback") is False

    def test_empty_invalid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("") is False

    def test_custom_scheme_no_path_or_netloc(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        # "myapp:" has scheme but no netloc or path
        assert _is_valid_redirect_uri("myapp:") is False

    def test_http_ipv6_localhost(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("http://[::1]/callback") is True

    def test_scheme_starts_with_digit_invalid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("1badscheme://callback") is False


# ---------------------------------------------------------------------------
# _get_external_url
# ---------------------------------------------------------------------------


class TestGetExternalUrl:
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    def test_no_proxy_headers_no_query(self, _):
        from auth.api.routes.oauth2.authorize import _get_external_url

        request = _mock_request(url_path="/oauth2/authorize", url_query="")
        result = _get_external_url(request)
        assert result == "https://auth.example.com/oauth2/authorize"

    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    def test_with_query(self, _):
        from auth.api.routes.oauth2.authorize import _get_external_url

        request = _mock_request(url_path="/oauth2/authorize", url_query="client_id=abc")
        result = _get_external_url(request)
        assert result == "https://auth.example.com/oauth2/authorize?client_id=abc"

    @patch(f"{MODULE}.get_tenant_prefix", return_value="/t/knowledge")
    def test_with_tenant_prefix(self, _):
        from auth.api.routes.oauth2.authorize import _get_external_url

        request = _mock_request(
            url_path="/oauth2/authorize",
            url_query="",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "auth.example.com"},
        )
        result = _get_external_url(request)
        assert result == "https://auth.example.com/t/knowledge/oauth2/authorize"

    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    def test_proxy_headers(self, _):
        from auth.api.routes.oauth2.authorize import _get_external_url

        request = _mock_request(
            url_path="/oauth2/authorize",
            url_query="foo=bar",
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "proxy.example.com"},
        )
        result = _get_external_url(request)
        assert result == "https://proxy.example.com/oauth2/authorize?foo=bar"


# ---------------------------------------------------------------------------
# render_oauth2_error
# ---------------------------------------------------------------------------


class TestRenderOauth2Error:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    async def test_renders_error_template(self, _):
        from auth.api.routes.oauth2.authorize import render_oauth2_error

        db = AsyncMock()
        branding_service = AsyncMock()
        branding_service.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await render_oauth2_error(
            db, branding_service, request, "invalid_request", "Something bad happened", 400
        )

        assert isinstance(result, HTMLResponse)
        assert result.status_code == 400
        branding_service.render_template.assert_awaited_once()
        call_args = branding_service.render_template.call_args
        assert call_args[0][1] == "oauth2/error.html"
        template_ctx = call_args[0][2]
        assert template_ctx["error"] == "invalid_request"
        assert template_ctx["error_description"] == "Something bad happened"


# ---------------------------------------------------------------------------
# authorize_get - Standard flow
# ---------------------------------------------------------------------------


class TestAuthorizeGetStandard:
    """Tests for the standard authorization request path (no PAR, no JAR)."""

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_missing_response_type(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type=None,
            redirect_uri="https://app.example.com/cb",
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_missing_redirect_uri(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type="code",
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_unsupported_response_type(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type="token",
            redirect_uri="https://app.example.com/cb",
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_redirect_uri_format(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type="code",
            redirect_uri="not-a-valid-uri",
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_unknown_client(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="unknown",
            response_type="code",
            redirect_uri="https://app.example.com/cb",
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_redirect_uri_not_registered(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=False)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://bad.example.com/cb",
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_scope_redirects(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=False)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="invalid_scope",
            state="s1",
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert "invalid_scope" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=True)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=True)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_pkce_required_but_missing(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer, mock_method, mock_challenge
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state="s1",
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code_challenge" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=True)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=False)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_pkce_invalid_method(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer, mock_method, mock_challenge
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state="s1",
            code_challenge="challenge123",
            code_challenge_method="plain",
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code_challenge_method" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=False)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=True)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_pkce_invalid_challenge(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer, mock_method, mock_challenge
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state="s1",
            code_challenge="bad!!!",
            code_challenge_method="S256",
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code_challenge" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_user_not_logged_in_redirects_to_login(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        # No session cookie
        request = _mock_request(cookies={})

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_prompt_login_forces_reauth(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        user = make_user()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        request = _mock_request(cookies={"session": "valid_token"})

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt="login",
            request_uri=None,
            request_param=None,
            db=db,
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "/auth/login" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value="t-1")
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_consent_required_shows_consent_page(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        client.require_consent = True
        user = make_user()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Consent</html>")
        request = _mock_request(cookies={"session": "valid_token"})

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)
        branding_svc.render_template.assert_awaited_once()
        call_args = branding_svc.render_template.call_args
        assert call_args[0][1] == "oauth2/consent.html"

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_no_consent_issues_code(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        client.require_consent = False
        user = make_user()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        oauth2_svc.create_authorization_code = AsyncMock(return_value="code_abc")
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        request = _mock_request(cookies={"session": "valid_token"})

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state="st1",
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param=None,
            db=db,
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code=code_abc" in result.headers["location"]
        assert "state=st1" in result.headers["location"]
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# authorize_get - PAR flow
# ---------------------------------------------------------------------------


class TestAuthorizeGetPAR:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_request_uri_format(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="bad:format:uri",
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_par_request_not_found(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        par_svc = AsyncMock()
        par_svc.get_par_request_for_client = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="urn:ietf:params:oauth:request_uri:abc123",
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=par_svc,
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_par_request_expired(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        par_request = MagicMock()
        par_svc = AsyncMock()
        par_svc.get_par_request_for_client = AsyncMock(return_value=par_request)
        par_svc.is_expired = MagicMock(return_value=True)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="urn:ietf:params:oauth:request_uri:abc123",
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=par_svc,
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_par_request_already_used(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        par_request = MagicMock()
        par_svc = AsyncMock()
        par_svc.get_par_request_for_client = AsyncMock(return_value=par_request)
        par_svc.is_expired = MagicMock(return_value=False)
        par_svc.is_used = MagicMock(return_value=True)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="urn:ietf:params:oauth:request_uri:abc123",
            request_param=None,
            db=db,
            session_service=AsyncMock(),
            oauth2_service=AsyncMock(),
            par_service=par_svc,
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_par_success_issues_code(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        par_request = MagicMock()
        par_request.response_type = "code"
        par_request.redirect_uri = "https://app.example.com/callback"
        par_request.scopes = ["openid"]
        par_request.state = "par_state"
        par_request.code_challenge = None
        par_request.code_challenge_method = None
        par_request.nonce = None
        par_request.prompt = None

        par_svc = AsyncMock()
        par_svc.get_par_request_for_client = AsyncMock(return_value=par_request)
        par_svc.is_expired = MagicMock(return_value=False)
        par_svc.is_used = MagicMock(return_value=False)
        par_svc.mark_as_used = AsyncMock()

        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        client.require_consent = False

        user = make_user()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.create_authorization_code = AsyncMock(return_value="par_code_xyz")

        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)

        request = _mock_request(cookies={"session": "valid_token"})

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="urn:ietf:params:oauth:request_uri:abc123",
            request_param=None,
            db=db,
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code=par_code_xyz" in result.headers["location"]
        assert "state=par_state" in result.headers["location"]


# ---------------------------------------------------------------------------
# authorize_get - JAR flow
# ---------------------------------------------------------------------------


class TestAuthorizeGetJAR:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_jar_unknown_client(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="unknown",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param="eyJhbGciOiJSUzI1NiJ9...",
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_jar_validation_failure(self, mock_cookie, mock_prefix, mock_tid, mock_issuer):
        from auth.api.routes.oauth2.authorize import authorize_get
        from auth.services.jar import JARError

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        jar_svc = MagicMock()
        jar_svc.validate_request_object = MagicMock(
            side_effect=JARError("invalid_request", "Bad JWT")
        )
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param="bad.jwt.token",
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=jar_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_jar_unsupported_response_type(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        db = AsyncMock()
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        jar_svc = MagicMock()
        jar_svc.validate_request_object = MagicMock(return_value={"response_type": "token"})
        jar_svc.extract_authorization_params = MagicMock(
            return_value={
                "response_type": "token",
                "redirect_uri": "https://app.example.com/callback",
                "scopes": ["openid"],
            }
        )
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")
        request = _mock_request()

        result = await authorize_get(
            request=request,
            client_id="test_client_id",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param="valid.jwt.token",
            db=db,
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=jar_svc,
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)


# ---------------------------------------------------------------------------
# authorize_post
# ---------------------------------------------------------------------------


class TestAuthorizePost:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_no_session_token_raises_401(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        request = _mock_request(cookies={})
        with pytest.raises(HTTPException) as exc_info:
            await authorize_post(
                request=request,
                consent="allow",
                client_id="test",
                redirect_uri="https://app.example.com/cb",
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                db=AsyncMock(),
                session_service=AsyncMock(),
                oauth2_service=AsyncMock(),
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_session_raises_401(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=None)
        request = _mock_request(cookies={"session": "bad_token"})

        with pytest.raises(HTTPException) as exc_info:
            await authorize_post(
                request=request,
                consent="allow",
                client_id="test",
                redirect_uri="https://app.example.com/cb",
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                db=AsyncMock(),
                session_service=session_svc,
                oauth2_service=AsyncMock(),
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_unknown_client_raises_400(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        user = make_user()
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)
        request = _mock_request(cookies={"session": "good_token"})

        with pytest.raises(HTTPException) as exc_info:
            await authorize_post(
                request=request,
                consent="allow",
                client_id="unknown",
                redirect_uri="https://app.example.com/cb",
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                db=AsyncMock(),
                session_service=session_svc,
                oauth2_service=oauth2_svc,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_invalid_redirect_uri_raises_400(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        user = make_user()
        client = make_oauth2_client()
        client.is_active = True
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=False)
        request = _mock_request(cookies={"session": "good_token"})

        with pytest.raises(HTTPException) as exc_info:
            await authorize_post(
                request=request,
                consent="allow",
                client_id="test_client_id",
                redirect_uri="https://bad.example.com/cb",
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                db=AsyncMock(),
                session_service=session_svc,
                oauth2_service=oauth2_svc,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_consent_denied_redirects(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        user = make_user()
        client = make_oauth2_client()
        client.is_active = True
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        request = _mock_request(cookies={"session": "good_token"})

        result = await authorize_post(
            request=request,
            consent="deny",
            client_id="test_client_id",
            redirect_uri="https://app.example.com/callback",
            scope=None,
            state="s1",
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            db=AsyncMock(),
            session_service=session_svc,
            oauth2_service=oauth2_svc,
        )

        assert isinstance(result, RedirectResponse)
        assert "access_denied" in result.headers["location"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_consent_allowed_issues_code(self, mock_cookie):
        from auth.api.routes.oauth2.authorize import authorize_post

        user = make_user()
        client = make_oauth2_client()
        client.is_active = True
        db = AsyncMock()
        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.create_authorization_code = AsyncMock(return_value="consent_code_abc")
        request = _mock_request(cookies={"session": "good_token"})

        result = await authorize_post(
            request=request,
            consent="allow",
            client_id="test_client_id",
            redirect_uri="https://app.example.com/callback",
            scope="openid profile",
            state="s2",
            code_challenge="ch",
            code_challenge_method="S256",
            nonce="n1",
            db=db,
            session_service=session_svc,
            oauth2_service=oauth2_svc,
        )

        assert isinstance(result, RedirectResponse)
        assert "code=consent_code_abc" in result.headers["location"]
        assert "state=s2" in result.headers["location"]
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# _is_valid_redirect_uri — remaining branches
# ---------------------------------------------------------------------------


class TestIsValidRedirectUriEdgeCases:
    def test_https_without_netloc_invalid(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        assert _is_valid_redirect_uri("https:///callback") is False

    def test_unparseable_uri_is_rejected(self):
        from auth.api.routes.oauth2.authorize import _is_valid_redirect_uri

        with patch(f"{MODULE}.urlparse", side_effect=ValueError("bad uri")):
            assert _is_valid_redirect_uri("https://example.com/cb") is False


# ---------------------------------------------------------------------------
# JAR flow — redirect_uri and scope validation
# ---------------------------------------------------------------------------


def _jar_service(response_type="code", redirect_uri="https://app.example.com/callback"):
    jar_svc = MagicMock()
    jar_svc.validate_request_object = MagicMock(return_value={"response_type": response_type})
    jar_svc.extract_authorization_params = MagicMock(
        return_value={
            "response_type": response_type,
            "redirect_uri": redirect_uri,
            "scopes": ["openid"],
        }
    )
    return jar_svc


async def _authorize_jar(oauth2_svc, jar_svc, branding_svc):
    from auth.api.routes.oauth2.authorize import authorize_get

    return await authorize_get(
        request=_mock_request(),
        client_id="test_client_id",
        response_type=None,
        redirect_uri=None,
        scope=None,
        state=None,
        code_challenge=None,
        code_challenge_method=None,
        nonce=None,
        prompt=None,
        request_uri=None,
        request_param="valid.jwt.token",
        db=AsyncMock(),
        session_service=AsyncMock(),
        oauth2_service=oauth2_svc,
        par_service=AsyncMock(),
        jar_service=jar_svc,
        branding_service=branding_svc,
    )


@patch(
    f"{MODULE}.get_issuer_from_context",
    new_callable=AsyncMock,
    return_value="https://auth.example.com",
)
@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}.get_session_cookie_name", return_value="session")
class TestAuthorizeGetJARValidation:
    @pytest.mark.asyncio
    async def test_jar_redirect_uri_not_registered(self, *_mocks):
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=False)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")

        result = await _authorize_jar(oauth2_svc, _jar_service(), branding_svc)

        assert isinstance(result, HTMLResponse)

    @pytest.mark.asyncio
    async def test_jar_invalid_scope_redirects(self, *_mocks):
        client = make_oauth2_client()
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=False)

        result = await _authorize_jar(oauth2_svc, _jar_service(), AsyncMock())

        assert isinstance(result, RedirectResponse)
        assert "error=invalid_scope" in result.headers["location"]


# ---------------------------------------------------------------------------
# PAR flow — client re-check
# ---------------------------------------------------------------------------


class TestAuthorizeGetPARUnknownClient:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_client_deactivated_after_par(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        par_request = MagicMock()
        par_request.response_type = "code"
        par_request.redirect_uri = "https://app.example.com/callback"
        par_request.scopes = ["openid"]
        par_request.state = None
        par_request.code_challenge = None
        par_request.code_challenge_method = None
        par_request.nonce = None
        par_request.prompt = None

        par_svc = AsyncMock()
        par_svc.get_par_request_for_client = AsyncMock(return_value=par_request)
        par_svc.is_expired = MagicMock(return_value=False)
        par_svc.is_used = MagicMock(return_value=False)
        par_svc.mark_as_used = AsyncMock()

        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)
        branding_svc = AsyncMock()
        branding_svc.render_template = AsyncMock(return_value="<html>Error</html>")

        result = await authorize_get(
            request=_mock_request(),
            client_id="test_client_id",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri="urn:ietf:params:oauth:request_uri:abc123",
            request_param=None,
            db=AsyncMock(),
            session_service=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            jar_service=MagicMock(),
            branding_service=branding_svc,
        )

        assert isinstance(result, HTMLResponse)


# ---------------------------------------------------------------------------
# PKCE method default + non-login prompt
# ---------------------------------------------------------------------------


@patch(
    f"{MODULE}.get_issuer_from_context",
    new_callable=AsyncMock,
    return_value="https://auth.example.com",
)
@patch(f"{MODULE}.get_current_tenant_id", return_value=None)
@patch(f"{MODULE}.get_tenant_prefix", return_value="")
@patch(f"{MODULE}.get_session_cookie_name", return_value="session")
class TestAuthorizeGetPkceAndPrompt:
    async def _run(self, *, code_challenge, code_challenge_method, prompt, require_pkce=False):
        from auth.api.routes.oauth2.authorize import authorize_get

        client = make_oauth2_client(require_pkce=require_pkce)
        client.is_active = True
        client.require_consent = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        oauth2_svc.create_authorization_code = AsyncMock(return_value="code_xyz")

        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=make_user())

        return await authorize_get(
            request=_mock_request(cookies={"session": "valid_token"}),
            client_id="test_client_id",
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            scope="openid",
            state=None,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=None,
            prompt=prompt,
            request_uri=None,
            request_param=None,
            db=AsyncMock(),
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=MagicMock(),
            branding_service=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_missing_method_defaults_to_s256(self, *_mocks):
        challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

        result = await self._run(
            code_challenge=challenge,
            code_challenge_method=None,
            prompt=None,
            require_pkce=True,
        )

        assert isinstance(result, RedirectResponse)
        assert "code=code_xyz" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_prompt_without_login_does_not_force_reauth(self, *_mocks):
        result = await self._run(code_challenge=None, code_challenge_method=None, prompt="consent")

        assert isinstance(result, RedirectResponse)
        assert "code=code_xyz" in result.headers["location"]


class TestAuthorizeGetJARSuccess:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    @patch(f"{MODULE}.get_current_tenant_id", return_value=None)
    @patch(f"{MODULE}.get_tenant_prefix", return_value="")
    @patch(f"{MODULE}.get_session_cookie_name", return_value="session")
    async def test_valid_request_object_issues_code(
        self, mock_cookie, mock_prefix, mock_tid, mock_issuer
    ):
        from auth.api.routes.oauth2.authorize import authorize_get

        client = make_oauth2_client(require_pkce=False)
        client.is_active = True
        client.require_consent = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        oauth2_svc.create_authorization_code = AsyncMock(return_value="jar_code")

        session_svc = AsyncMock()
        session_svc.get_user_by_session_token = AsyncMock(return_value=make_user())

        result = await authorize_get(
            request=_mock_request(cookies={"session": "valid_token"}),
            client_id="test_client_id",
            response_type=None,
            redirect_uri=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
            request_uri=None,
            request_param="valid.jwt.token",
            db=AsyncMock(),
            session_service=session_svc,
            oauth2_service=oauth2_svc,
            par_service=AsyncMock(),
            jar_service=_jar_service(),
            branding_service=AsyncMock(),
        )

        assert isinstance(result, RedirectResponse)
        assert "code=jar_code" in result.headers["location"]
