# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for federation routes — callback and providers."""

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

CALLBACK_MODULE = "auth.api.routes.federation.callback"
PROVIDERS_MODULE = "auth.api.routes.federation.providers"


def _mock_request(headers=None, host="auth.example.com", scheme="https", client_host="10.0.0.1"):
    request = MagicMock()
    _headers = headers or {}
    request.headers = MagicMock()
    request.headers.get = MagicMock(side_effect=lambda k, d=None: _headers.get(k, d))
    request.url = MagicMock()
    request.url.scheme = scheme
    request.url.netloc = host
    request.client = MagicMock()
    request.client.host = client_host
    return request


def _encode_state(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


# ---------------------------------------------------------------------------
# Federation callback
# ---------------------------------------------------------------------------


class TestFederationCallback:
    @pytest.mark.asyncio
    async def test_error_from_idp(self):
        from auth.api.routes.federation.callback import federation_callback

        request = _mock_request()
        db = AsyncMock()

        result = await federation_callback(
            request,
            db,
            code=None,
            state=None,
            error="access_denied",
            error_description="User denied",
        )

        assert result.status_code == 302
        assert "federation_failed" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_missing_code_and_state(self):
        from auth.api.routes.federation.callback import federation_callback

        request = _mock_request()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await federation_callback(
                request, db, code=None, state=None, error=None, error_description=None
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_state(self):
        from auth.api.routes.federation.callback import federation_callback

        request = _mock_request()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await federation_callback(
                request, db, code="code123", state="invalid!!!", error=None, error_description=None
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_tenant_in_state(self):
        from auth.api.routes.federation.callback import federation_callback

        request = _mock_request()
        db = AsyncMock()
        state = _encode_state({"idp_id": "x"})

        with pytest.raises(HTTPException) as exc:
            await federation_callback(
                request, db, code="code123", state=state, error=None, error_description=None
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_idp_not_found(self, mock_fed):
        from auth.api.routes.federation.callback import federation_callback

        mock_fed.get_identity_provider = AsyncMock(return_value=None)

        request = _mock_request()
        db = AsyncMock()
        state = _encode_state({"tenant_slug": "acme", "idp_id": "x"})

        with pytest.raises(HTTPException) as exc:
            await federation_callback(
                request, db, code="code123", state=state, error=None, error_description=None
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value="session_id")
    @patch("auth.middlewares.tenant.get_csrf_cookie_name", return_value="csrf_token")
    @patch("auth.middlewares.tenant.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{CALLBACK_MODULE}.settings")
    @patch(f"{CALLBACK_MODULE}.hash_token", return_value="hashed")
    @patch(f"{CALLBACK_MODULE}.SessionService")
    @patch("auth.db.models.user.Session")
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_success(
        self,
        mock_fed,
        MockSession,
        MockSvc,
        mock_hash,
        mock_settings,
        mock_domain,
        mock_csrf,
        mock_cookie,
    ):
        from auth.api.routes.federation.callback import federation_callback

        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        idp = MagicMock()
        idp.name = "Google"
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)
        mock_fed.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "at", "id_token": "it"}
        )

        user_info = MagicMock()
        user_info.subject = "goog-123"
        user_info.email = "u@g.com"
        mock_fed.get_user_info = AsyncMock(return_value=user_info)

        user = MagicMock()
        user.id = uuid.uuid4()
        mock_fed.find_or_create_user = AsyncMock(return_value=(user, MagicMock(), True))

        svc_instance = MagicMock()
        svc_instance.generate_session_token.return_value = "sess-tok"
        svc_instance.generate_csrf_token.return_value = "csrf-tok"
        svc_instance.add = AsyncMock()
        MockSvc.return_value = svc_instance

        request = _mock_request(
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "auth.example.com"}
        )
        db = AsyncMock()
        db.add = MagicMock()
        state = _encode_state({"tenant_slug": "acme", "idp_id": "x", "redirect_uri": "/dashboard"})

        result = await federation_callback(
            request, db, code="code123", state=state, error=None, error_description=None
        )

        assert result.status_code == 302
        assert "/dashboard" in result.headers.get("location", "")
        svc_instance.add.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_value_error_during_exchange(self, mock_fed):
        from auth.api.routes.federation.callback import federation_callback

        idp = MagicMock()
        idp.name = "Google"
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)
        mock_fed.exchange_code_for_tokens = AsyncMock(side_effect=ValueError("No access token"))

        request = _mock_request(
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "auth.example.com"}
        )
        db = AsyncMock()
        state = _encode_state({"tenant_slug": "acme", "idp_id": "x"})

        result = await federation_callback(
            request, db, code="code123", state=state, error=None, error_description=None
        )

        assert result.status_code == 302
        assert "federation_failed" in result.headers.get("location", "")

    @pytest.mark.asyncio
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_unexpected_exception(self, mock_fed):
        from auth.api.routes.federation.callback import federation_callback

        idp = MagicMock()
        idp.name = "Google"
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)
        mock_fed.exchange_code_for_tokens = AsyncMock(side_effect=RuntimeError("oops"))

        request = _mock_request(
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "auth.example.com"}
        )
        db = AsyncMock()
        state = _encode_state({"tenant_slug": "acme", "idp_id": "x"})

        result = await federation_callback(
            request, db, code="code123", state=state, error=None, error_description=None
        )

        assert result.status_code == 302
        location = result.headers.get("location", "").lower()
        assert "federation_failed" in location


# ---------------------------------------------------------------------------
# Federation providers — list_providers
# ---------------------------------------------------------------------------


class TestListProviders:
    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context", return_value=None)
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_no_tenant(self, mock_fed, _ctx):
        from auth.api.routes.federation.providers import list_providers

        with pytest.raises(HTTPException) as exc:
            await list_providers(AsyncMock(), tenant_slug=None)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context", return_value=None)
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_with_query_slug(self, mock_fed, _ctx):
        from auth.api.routes.federation.providers import list_providers

        idp = MagicMock()
        idp.id = uuid.uuid4()
        idp.name = "Google"
        idp.provider_type = MagicMock()
        idp.provider_type.value = "google"
        idp.icon_url = "https://g.com/icon.png"
        idp.button_text = "Sign in with Google"
        mock_fed.get_tenant_identity_providers = AsyncMock(return_value=[idp])

        result = await list_providers(AsyncMock(), tenant_slug="acme")

        assert result.tenant_slug == "acme"
        assert len(result.providers) == 1
        assert result.providers[0].name == "Google"

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context")
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_with_context_slug(self, mock_fed, mock_ctx):
        from auth.api.routes.federation.providers import list_providers

        ctx = MagicMock()
        ctx.tenant_slug = "context-tenant"
        mock_ctx.return_value = ctx
        mock_fed.get_tenant_identity_providers = AsyncMock(return_value=[])

        result = await list_providers(AsyncMock(), tenant_slug=None)

        assert result.tenant_slug == "context-tenant"
        assert result.providers == []

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context", return_value=None)
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_button_text_default(self, mock_fed, _ctx):
        from auth.api.routes.federation.providers import list_providers

        idp = MagicMock()
        idp.id = uuid.uuid4()
        idp.name = "GitHub"
        idp.provider_type = MagicMock()
        idp.provider_type.value = "github"
        idp.icon_url = None
        idp.button_text = None  # Should use default
        mock_fed.get_tenant_identity_providers = AsyncMock(return_value=[idp])

        result = await list_providers(AsyncMock(), tenant_slug="acme")

        assert result.providers[0].button_text == "Continue with GitHub"


# ---------------------------------------------------------------------------
# Federation providers — initiate_federation
# ---------------------------------------------------------------------------


class TestInitiateFederation:
    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context", return_value=None)
    async def test_no_tenant_context(self, _ctx):
        from auth.api.routes.federation.providers import initiate_federation

        request = _mock_request()

        with pytest.raises(HTTPException) as exc:
            await initiate_federation(request, "idp-1", AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context")
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_idp_not_found(self, mock_fed, mock_ctx):
        from auth.api.routes.federation.providers import initiate_federation

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        mock_ctx.return_value = ctx
        mock_fed.get_identity_provider = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await initiate_federation(_mock_request(), "idp-1", AsyncMock())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context")
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_idp_inactive(self, mock_fed, mock_ctx):
        from auth.api.routes.federation.providers import initiate_federation

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        mock_ctx.return_value = ctx

        idp = MagicMock()
        idp.is_active = False
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)

        with pytest.raises(HTTPException) as exc:
            await initiate_federation(_mock_request(), "idp-1", AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    @patch(f"{PROVIDERS_MODULE}.FederationService")
    @patch(f"{PROVIDERS_MODULE}.get_tenant_context")
    @patch(f"{PROVIDERS_MODULE}.federation_service")
    async def test_success(self, mock_fed, mock_ctx, MockFedClass):
        from auth.api.routes.federation.providers import initiate_federation

        ctx = MagicMock()
        ctx.tenant_slug = "acme"
        mock_ctx.return_value = ctx

        idp = MagicMock()
        idp.id = uuid.uuid4()
        idp.is_active = True
        idp.name = "Google"
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)

        MockFedClass.generate_nonce.return_value = "nonce123"
        MockFedClass.generate_code_verifier.return_value = "verifier123"
        MockFedClass.generate_state.return_value = "state123"

        mock_fed.get_authorization_url = AsyncMock(
            return_value="https://accounts.google.com/auth?..."
        )

        request = _mock_request(
            headers={"x-forwarded-proto": "https", "x-forwarded-host": "auth.example.com"}
        )

        result = await initiate_federation(
            request, str(idp.id), AsyncMock(), redirect_uri=None, state=None
        )

        assert result.status_code == 302
        assert "accounts.google.com" in result.headers.get("location", "")


class TestFederationCallbackRedirectResolution:
    """The final redirect: state passthrough and the default settings landing page."""

    def _prime(self, mock_fed, mock_svc, mock_settings):
        mock_settings.session_expiry_days = 7
        mock_settings.session_cookie_secure = True

        idp = MagicMock()
        idp.name = "Google"
        mock_fed.get_identity_provider = AsyncMock(return_value=idp)
        mock_fed.exchange_code_for_tokens = AsyncMock(
            return_value={"access_token": "at", "id_token": "it"}
        )
        mock_fed.get_user_info = AsyncMock(return_value=MagicMock())
        user = MagicMock()
        user.id = uuid.uuid4()
        mock_fed.find_or_create_user = AsyncMock(return_value=(user, MagicMock(), True))

        svc_instance = MagicMock()
        svc_instance.generate_session_token.return_value = "sess-tok"
        svc_instance.generate_csrf_token.return_value = "csrf-tok"
        svc_instance.add = AsyncMock()
        mock_svc.return_value = svc_instance

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value="session_id")
    @patch("auth.middlewares.tenant.get_csrf_cookie_name", return_value="csrf_token")
    @patch("auth.middlewares.tenant.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{CALLBACK_MODULE}.settings")
    @patch(f"{CALLBACK_MODULE}.hash_token", return_value="hashed")
    @patch(f"{CALLBACK_MODULE}.SessionService")
    @patch("auth.db.models.user.Session")
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_original_state_is_appended(
        self,
        mock_fed,
        MockSession,
        MockSvc,
        mock_hash,
        mock_settings,
        mock_domain,
        mock_csrf,
        mock_cookie,
    ):
        from auth.api.routes.federation.callback import federation_callback

        self._prime(mock_fed, MockSvc, mock_settings)

        db = AsyncMock()
        db.add = MagicMock()
        state = _encode_state(
            {
                "tenant_slug": "acme",
                "idp_id": "x",
                "redirect_uri": "/dashboard?tab=1",
                "original_state": "abc123",
            }
        )

        result = await federation_callback(
            _mock_request(), db, code="code123", state=state, error=None, error_description=None
        )

        assert result.headers["location"] == "/dashboard?tab=1&state=abc123"

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value="session_id")
    @patch("auth.middlewares.tenant.get_csrf_cookie_name", return_value="csrf_token")
    @patch("auth.middlewares.tenant.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{CALLBACK_MODULE}.settings")
    @patch(f"{CALLBACK_MODULE}.hash_token", return_value="hashed")
    @patch(f"{CALLBACK_MODULE}.SessionService")
    @patch("auth.db.models.user.Session")
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_state_uses_question_mark_when_no_query(
        self,
        mock_fed,
        MockSession,
        MockSvc,
        mock_hash,
        mock_settings,
        mock_domain,
        mock_csrf,
        mock_cookie,
    ):
        from auth.api.routes.federation.callback import federation_callback

        self._prime(mock_fed, MockSvc, mock_settings)

        db = AsyncMock()
        db.add = MagicMock()
        state = _encode_state(
            {
                "tenant_slug": "acme",
                "idp_id": "x",
                "redirect_uri": "/dashboard",
                "original_state": "abc123",
            }
        )

        result = await federation_callback(
            _mock_request(), db, code="code123", state=state, error=None, error_description=None
        )

        assert result.headers["location"] == "/dashboard?state=abc123"

    @pytest.mark.asyncio
    @patch("auth.middlewares.tenant.get_session_cookie_name", return_value="session_id")
    @patch("auth.middlewares.tenant.get_csrf_cookie_name", return_value="csrf_token")
    @patch("auth.middlewares.tenant.get_session_cookie_domain", return_value=".example.com")
    @patch(f"{CALLBACK_MODULE}.settings")
    @patch(f"{CALLBACK_MODULE}.hash_token", return_value="hashed")
    @patch(f"{CALLBACK_MODULE}.SessionService")
    @patch("auth.db.models.user.Session")
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_no_redirect_uri_lands_on_settings(
        self,
        mock_fed,
        MockSession,
        MockSvc,
        mock_hash,
        mock_settings,
        mock_domain,
        mock_csrf,
        mock_cookie,
    ):
        from auth.api.routes.federation.callback import federation_callback

        self._prime(mock_fed, MockSvc, mock_settings)

        db = AsyncMock()
        db.add = MagicMock()
        state = _encode_state({"tenant_slug": "acme", "idp_id": "x"})

        result = await federation_callback(
            _mock_request(), db, code="code123", state=state, error=None, error_description=None
        )

        assert result.headers["location"] == "/auth/settings"


class TestFederationCallbackMissingAccessToken:
    @pytest.mark.asyncio
    @patch(f"{CALLBACK_MODULE}.federation_service")
    async def test_token_response_without_access_token_redirects_to_login(self, mock_fed):
        from auth.api.routes.federation.callback import federation_callback

        mock_fed.get_identity_provider = AsyncMock(return_value=MagicMock())
        mock_fed.exchange_code_for_tokens = AsyncMock(return_value={"id_token": "it"})

        state = _encode_state({"tenant_slug": "acme", "idp_id": "x"})

        result = await federation_callback(
            _mock_request(),
            AsyncMock(),
            code="code123",
            state=state,
            error=None,
            error_description=None,
        )

        assert result.status_code == 302
        assert "error=federation_failed" in result.headers["location"]
        assert "No%20access%20token%20in%20response" in result.headers["location"]


# ---------------------------------------------------------------------------
# The login page announces a failed federation
# ---------------------------------------------------------------------------


class TestLoginPageFederationFailure:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("code", "shown"), [("federation_failed", True), ("unknown_code", False), ("", False)]
    )
    @patch("auth.api.routes.auth.login.get_current_tenant_id", return_value=None)
    @patch("auth.api.routes.auth.login.get_tenant_prefix", return_value="")
    async def test_only_known_error_codes_are_shown(self, mock_prefix, mock_tid, code, shown):
        from auth.api.routes.auth.login import login_form

        branding_svc = MagicMock()
        branding_svc.render_template = AsyncMock(return_value="<html></html>")
        request = _mock_request()
        request.cookies = {}

        await login_form(request, AsyncMock(), MagicMock(), branding_svc, error=code)

        context = branding_svc.render_template.call_args[0][2]
        assert bool(context["error"]) is shown
        if shown:
            assert "identity provider" in context["error"]
