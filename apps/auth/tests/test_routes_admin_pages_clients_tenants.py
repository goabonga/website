# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for admin HTML pages: clients_pages.py and tenants_pages.py — 100% mocked."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from tests.conftest import (
    make_access_token,
    make_execute_result,
    make_refresh_token,
    make_user,
)

# Module paths for patching
CLIENTS_PAGES = "auth.api.routes.admin.clients_pages"
TENANTS_PAGES = "auth.api.routes.admin.tenants_pages"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(UTC)


def _make_auth():
    """Create a standard (user, roles) auth tuple."""
    user = make_user()
    roles = [MagicMock()]
    return (user, roles)


def _mock_request(query_params=None, form_data=None):
    """Create a mock Request with query_params and optional form data."""
    request = MagicMock()
    request.query_params = query_params or {}
    if form_data is not None:

        async def _form():
            return form_data

        request.form = _form
    else:
        request.form = AsyncMock(return_value={})
    return request


def _mock_templates():
    """Create a mock templates object that get_templates() returns."""
    templates = MagicMock()
    templates.TemplateResponse.return_value = MagicMock()
    return templates


def _make_client_for_pages(
    client_id_str=None,
    is_confidential=True,
    is_active=True,
):
    """Create a mock OAuth2Client with all fields needed by client_to_dict."""
    client = MagicMock()
    client.id = uuid.uuid4()
    client.client_id = client_id_str or "test_client_abc"
    client.name = "Test App"
    client.description = "A test client"
    client.homepage_url = "https://app.example.com"
    client.redirect_uris = ["https://app.example.com/callback"]
    client.allowed_scopes = ["openid", "profile", "email"]
    client.allowed_grant_types = ["authorization_code", "refresh_token"]
    client.token_endpoint_auth_method = "client_secret_basic"
    client.is_confidential = is_confidential
    client.is_active = is_active
    client.require_pkce = True
    client.require_consent = True
    client.allowed_origins = ["https://app.example.com"]
    client.jwks_uri = None
    client.access_token_expiry_seconds = 3600
    client.refresh_token_expiry_seconds = 86400
    client.client_secret_hash = "hashed" if is_confidential else None
    client.created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
    client.updated_at = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
    return client


def _make_scope(name="users:read", resource="users", action="read", description=None):
    """Create a mock Scope model."""
    scope = MagicMock()
    scope.name = name
    scope.resource = resource
    scope.action = action
    scope.description = description or f"{resource}:{action}"
    scope.is_active = True
    return scope


def _make_tenant_for_pages(
    slug="acme",
    display_name="Acme Corp",
    custom_domain=None,
    is_active=True,
    is_platform=False,
    members=None,
    identity_providers=None,
    roles=None,
):
    """Create a mock Tenant model for pages tests."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.slug = slug
    t.display_name = display_name
    t.custom_domain = custom_domain
    t.is_active = is_active
    t.is_platform = is_platform
    t.settings = {}
    t.members = members or []
    t.identity_providers = identity_providers or []
    t.roles = roles or []
    t.branding = None
    t.templates = []
    t.created_at = _now()
    t.updated_at = _now()
    return t


def _make_member(user_id=None, role_name="member", role_display_name="Member", role_id=None):
    """Create a mock TenantMember."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.user_id = user_id or uuid.uuid4()
    m.tenant_id = uuid.uuid4()
    m.role_name = role_name
    m.role_display_name = role_display_name
    m.role_id = role_id or uuid.uuid4()
    m.joined_at = _now()
    m.invited_at = _now()
    m.created_at = _now()
    m.user = MagicMock()
    m.user.profile = MagicMock()
    m.user.profile.name = "Test User"
    m.custom_role = MagicMock()
    m.custom_role.name = role_name
    m.custom_role.display_name = role_display_name
    return m


def _make_idp(tenant_id=None, name="Google SSO", is_active=True, is_default=False):
    """Create a mock IdentityProvider."""
    from auth.db.models.tenant import IdentityProviderType

    idp = MagicMock()
    idp.id = uuid.uuid4()
    idp.tenant_id = tenant_id or uuid.uuid4()
    idp.name = name
    idp.provider_type = IdentityProviderType.OIDC
    idp.client_id = "google-client-id"
    idp.client_secret_encrypted = b"encrypted"
    idp.discovery_url = "https://accounts.google.com/.well-known/openid-configuration"
    idp.scopes = ["openid", "profile", "email"]
    idp.is_active = is_active
    idp.is_default = is_default
    idp.auto_provision = True
    idp.allow_linking = True
    idp.icon_url = None
    idp.button_text = "Sign in with Google"
    idp.display_order = 0
    idp.federated_identities = []
    idp.created_at = _now()
    idp.updated_at = _now()
    return idp


def _make_custom_role(
    name="member", display_name="Member", is_system=True, display_order=0, scopes=None
):
    """Create a mock TenantCustomRole."""
    r = MagicMock()
    r.id = uuid.uuid4()
    r.name = name
    r.display_name = display_name
    r.description = f"Role: {display_name}"
    r.scopes = scopes or ["members:read"]
    r.is_system = is_system
    r.display_order = display_order
    return r


def _make_form_data(data_dict):
    """Create a mock form data object."""
    form = MagicMock()
    form.get = lambda key, default="": data_dict.get(key, default)
    form.items = lambda: data_dict.items()
    form.getlist = lambda key: data_dict.get(key, [])
    return form


# ===========================================================================
# CLIENTS PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# client_to_dict
# ---------------------------------------------------------------------------


class TestClientToDict:
    def test_converts_all_fields(self):
        from auth.api.routes.admin.clients_pages import client_to_dict

        client = _make_client_for_pages()
        result = client_to_dict(client)

        assert result["id"] == str(client.id)
        assert result["client_id"] == "test_client_abc"
        assert result["name"] == "Test App"
        assert result["description"] == "A test client"
        assert result["homepage_url"] == "https://app.example.com"
        assert result["redirect_uris"] == ["https://app.example.com/callback"]
        assert result["is_confidential"] is True
        assert result["is_active"] is True

    def test_none_timestamps(self):
        from auth.api.routes.admin.clients_pages import client_to_dict

        client = _make_client_for_pages()
        client.created_at = None
        client.updated_at = None
        result = client_to_dict(client)

        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_isoformat_timestamps(self):
        from auth.api.routes.admin.clients_pages import client_to_dict

        client = _make_client_for_pages()
        result = client_to_dict(client)

        assert result["created_at"] == client.created_at.isoformat()
        assert result["updated_at"] == client.updated_at.isoformat()


# ---------------------------------------------------------------------------
# token_to_dict
# ---------------------------------------------------------------------------


class TestTokenToDict:
    def test_active_token(self):
        from auth.api.routes.admin.clients_pages import token_to_dict

        token = make_access_token(expires_at=_now() + timedelta(hours=1))
        token.revoked_at = None
        result = token_to_dict(token, user_email="user@example.com")

        assert result["id"] == str(token.id)
        assert result["jti"] == token.jti
        assert result["user_email"] == "user@example.com"
        assert result["is_active"] is True
        assert result["is_revoked"] is False
        assert result["is_expired"] is False

    def test_revoked_token(self):
        from auth.api.routes.admin.clients_pages import token_to_dict

        token = make_access_token(
            revoked_at=_now(),
            expires_at=_now() + timedelta(hours=1),
        )
        result = token_to_dict(token)

        assert result["is_active"] is False
        assert result["is_revoked"] is True

    def test_expired_token(self):
        from auth.api.routes.admin.clients_pages import token_to_dict

        token = make_access_token(expires_at=_now() - timedelta(hours=1))
        token.revoked_at = None
        result = token_to_dict(token)

        assert result["is_active"] is False
        assert result["is_expired"] is True

    def test_no_user_id(self):
        from auth.api.routes.admin.clients_pages import token_to_dict

        token = make_access_token()
        token.user_id = None
        token.revoked_at = None
        result = token_to_dict(token)

        assert result["user_id"] is None

    def test_none_timestamps(self):
        from auth.api.routes.admin.clients_pages import token_to_dict

        token = make_access_token()
        token.revoked_at = None
        token.created_at = None
        token.expires_at = _now() + timedelta(hours=1)
        result = token_to_dict(token)

        assert result["created_at"] is None
        assert result["revoked_at"] is None


# ---------------------------------------------------------------------------
# get_available_scopes
# ---------------------------------------------------------------------------


class TestGetAvailableScopes:
    async def test_returns_oidc_and_system_scopes(self):
        from auth.api.routes.admin.clients_pages import get_available_scopes

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await get_available_scopes(db)

        assert "oidc" in result
        assert "system" in result
        assert len(result["oidc"]) == 4
        assert any(s["name"] == "openid" for s in result["oidc"])

    async def test_adds_db_scopes_grouped_by_resource(self):
        from auth.api.routes.admin.clients_pages import get_available_scopes

        scope1 = _make_scope(name="users:read", resource="users", action="read")
        scope2 = _make_scope(name="users:write", resource="users", action="write")
        scope3 = _make_scope(name="clients:read", resource="clients", action="read")

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=make_execute_result(scalars_list=[scope1, scope2, scope3])
        )

        result = await get_available_scopes(db)

        assert "users" in result
        assert len(result["users"]) == 2
        assert "clients" in result
        assert len(result["clients"]) == 1

    async def test_scope_with_no_description_uses_fallback(self):
        from auth.api.routes.admin.clients_pages import get_available_scopes

        scope = _make_scope(
            name="custom:action", resource="custom", action="action", description=None
        )
        scope.description = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[scope]))

        result = await get_available_scopes(db)

        assert result["custom"][0]["description"] == "custom:action"


# ---------------------------------------------------------------------------
# generate_client_id / generate_client_secret
# ---------------------------------------------------------------------------


class TestGenerateClientIdPages:
    def test_returns_string(self):
        from auth.api.routes.admin.clients_pages import generate_client_id

        result = generate_client_id()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_different_each_time(self):
        from auth.api.routes.admin.clients_pages import generate_client_id

        assert generate_client_id() != generate_client_id()


class TestGenerateClientSecretPages:
    def test_returns_string(self):
        from auth.api.routes.admin.clients_pages import generate_client_secret

        result = generate_client_secret()
        assert isinstance(result, str)

    def test_different_each_time(self):
        from auth.api.routes.admin.clients_pages import generate_client_secret

        assert generate_client_secret() != generate_client_secret()


# ---------------------------------------------------------------------------
# clients_list_page
# ---------------------------------------------------------------------------


class TestClientsListPage:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={"can_view_clients": True})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_returns_template_response(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = None
        db = AsyncMock()
        # 1: count, 2: paginated clients, 3: tenants dropdown
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_execute_result(scalars_list=[client]),
                make_execute_result(all_rows=[]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        await clients_list_page(
            request=request, db=db, auth=auth, page=1, search=None, tenant_filter=None
        )
        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["active_section"] == "clients"
        assert ctx["total"] == 1
        assert len(ctx["clients"]) == 1

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_with_search(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_execute_result(scalars_list=[]),
                make_execute_result(all_rows=[]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        await clients_list_page(
            request=request, db=db, auth=auth, page=1, search="test", tenant_filter=None
        )
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["search"] == "test"
        assert ctx["total"] == 0

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_with_success_message(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_execute_result(scalars_list=[]),
                make_execute_result(all_rows=[]),
            ]
        )

        request = _mock_request(query_params={"success": "Done"})
        auth = _make_auth()

        await clients_list_page(
            request=request, db=db, auth=auth, page=1, search=None, tenant_filter=None
        )
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["success"] == "Done"

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_pagination_total_pages(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=45),
                make_execute_result(scalars_list=[]),
                make_execute_result(all_rows=[]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        await clients_list_page(
            request=request, db=db, auth=auth, page=2, search=None, tenant_filter=None
        )
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total_pages"] == 3  # ceil(45/20)
        assert ctx["page"] == 2


# ---------------------------------------------------------------------------
# client_create_page
# ---------------------------------------------------------------------------


class TestClientCreatePage:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    @patch(f"{CLIENTS_PAGES}.get_available_scopes")
    async def test_returns_create_form(self, mock_scopes, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_create_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates
        mock_scopes.return_value = {"oidc": [], "system": []}

        request = _mock_request(query_params={})
        db = AsyncMock()
        # db.execute is called once for the tenants dropdown
        db.execute = AsyncMock(return_value=make_execute_result(all_rows=[]))
        auth = _make_auth()

        await client_create_page(request=request, db=db, auth=auth)
        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["active_section"] == "clients"
        assert "available_scopes" in ctx
        assert "tenants" in ctx


# ---------------------------------------------------------------------------
# client_create_submit
# ---------------------------------------------------------------------------


class TestClientCreateSubmit:
    @patch(f"{CLIENTS_PAGES}.hash_password", return_value="hashed")
    @patch(f"{CLIENTS_PAGES}.generate_client_secret", return_value="secret123")
    @patch(f"{CLIENTS_PAGES}.generate_client_id", return_value="client_id_123")
    async def test_create_confidential_client(self, mock_gen_id, mock_gen_secret, mock_hash):
        from auth.api.routes.admin.clients_pages import client_create_submit

        form_data = _make_form_data(
            {
                "name": "New App",
                "description": "desc",
                "homepage_url": "",
                "redirect_uris": "https://example.com/cb",
                "is_confidential": "true",
                "grant_authorization_code": "true",
                "scope_openid": "true",
                "scope_profile": "true",
                "require_pkce": "true",
                "require_consent": "true",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
                "allowed_origins": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.refresh = AsyncMock()
        mock_client = MagicMock()
        mock_client.id = uuid.uuid4()

        # After refresh, the client mock should have an id
        async def _refresh(obj):
            obj.id = mock_client.id

        db.refresh = _refresh

        auth = _make_auth()

        result = await client_create_submit(request=request, db=db, auth=auth)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "new_secret=secret123" in result.headers.get("location", "")

    async def test_create_no_grant_type_redirects_error(self):
        from auth.api.routes.admin.clients_pages import client_create_submit

        form_data = _make_form_data(
            {
                "name": "New App",
                "redirect_uris": "https://example.com/cb",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await client_create_submit(request=request, db=db, auth=auth)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "grant+type+required" in result.headers.get("location", "")

    async def test_create_auth_code_without_redirect_uri(self):
        from auth.api.routes.admin.clients_pages import client_create_submit

        form_data = _make_form_data(
            {
                "name": "New App",
                "redirect_uris": "",
                "grant_authorization_code": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await client_create_submit(request=request, db=db, auth=auth)
        assert isinstance(result, RedirectResponse)
        assert "Redirect+URI+required" in result.headers.get("location", "")

    @patch(f"{CLIENTS_PAGES}.generate_client_id", return_value="id_123")
    async def test_create_public_client_no_secret(self, mock_gen_id):
        from auth.api.routes.admin.clients_pages import client_create_submit

        form_data = _make_form_data(
            {
                "name": "Public App",
                "redirect_uris": "",
                "grant_client_credentials": "true",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
                "allowed_origins": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()

        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db.refresh = _refresh
        auth = _make_auth()

        result = await client_create_submit(request=request, db=db, auth=auth)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "new_secret" not in result.headers.get("location", "")

    @patch(f"{CLIENTS_PAGES}.generate_client_id", side_effect=Exception("DB error"))
    async def test_create_handles_exception(self, mock_gen_id):
        from auth.api.routes.admin.clients_pages import client_create_submit

        form_data = _make_form_data(
            {
                "name": "App",
                "redirect_uris": "",
                "grant_client_credentials": "true",
                "allowed_origins": "",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await client_create_submit(request=request, db=db, auth=auth)
        assert isinstance(result, RedirectResponse)
        assert "error=" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_detail_page
# ---------------------------------------------------------------------------


class TestClientDetailPage:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_client_found_by_uuid(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = None
        client_id = str(client.id)

        db = AsyncMock()
        # Order: client lookup, tokens, total tokens, active tokens
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),  # client lookup
                make_execute_result(scalars_list=[]),  # tokens
                make_execute_result(scalar_value=0),  # total tokens count
                make_execute_result(scalar_value=0),  # active tokens count
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        await client_detail_page(
            request=request,
            client_id=client_id,
            db=db,
            auth=auth,
            tokens_page=1,
        )
        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["client"]["name"] == "Test App"

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_client_not_found_raises_404(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await client_detail_page(
                request=request,
                client_id=str(uuid.uuid4()),
                db=db,
                auth=auth,
                tokens_page=1,
            )
        assert exc_info.value.status_code == 404

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_client_found_by_string_id(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalars_list=[]),
                make_execute_result(scalar_value=0),
                make_execute_result(scalar_value=0),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        # Use a non-UUID string to trigger the ValueError path
        await client_detail_page(
            request=request,
            client_id="not-a-uuid",
            db=db,
            auth=auth,
            tokens_page=1,
        )
        templates.TemplateResponse.assert_called_once()

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_detail_with_tokens(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = None
        token = make_access_token(client_id=client.id)
        token.revoked_at = None
        token.user_id = uuid.uuid4()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalars_list=[token]),
                make_execute_result(scalar_value="user@test.com"),  # email lookup
                make_execute_result(scalar_value=1),  # total tokens
                make_execute_result(scalar_value=1),  # active tokens
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        await client_detail_page(
            request=request,
            client_id=str(client.id),
            db=db,
            auth=auth,
            tokens_page=1,
        )
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert len(ctx["tokens"]) == 1
        assert ctx["total_tokens"] == 1


# ---------------------------------------------------------------------------
# client_edit_page
# ---------------------------------------------------------------------------


class TestClientEditPage:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_available_scopes")
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_edit_page_found(self, mock_get_tpl, mock_scopes, mock_perms):
        from auth.api.routes.admin.clients_pages import client_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates
        mock_scopes.return_value = {"oidc": []}

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))

        request = _mock_request(query_params={})
        auth = _make_auth()

        await client_edit_page(request=request, client_id=str(client.id), db=db, auth=auth)
        templates.TemplateResponse.assert_called_once()

    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_edit_page_not_found(self, mock_get_tpl):
        from auth.api.routes.admin.clients_pages import client_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await client_edit_page(request=request, client_id=str(uuid.uuid4()), db=db, auth=auth)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# client_edit_submit
# ---------------------------------------------------------------------------


class TestClientEditSubmit:
    async def test_edit_client_not_found(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        form_data = _make_form_data({"name": "Updated"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(uuid.uuid4()), db=db, auth=auth
        )
        assert isinstance(result, RedirectResponse)
        assert "Client+not+found" in result.headers.get("location", "")

    async def test_edit_no_grant_type(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages()
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert "grant+type+required" in result.headers.get("location", "")

    async def test_edit_auth_code_no_redirect_uri(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages()
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "",
                "grant_authorization_code": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert "Redirect+URI+required" in result.headers.get("location", "")

    @patch(f"{CLIENTS_PAGES}.hash_password", return_value="hashed_new")
    @patch(f"{CLIENTS_PAGES}.generate_client_secret", return_value="new_secret_456")
    async def test_edit_public_to_confidential_generates_secret(self, mock_gen, mock_hash):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages(is_confidential=False)
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "",
                "grant_client_credentials": "true",
                "is_confidential": "true",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
                "allowed_origins": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert "new_secret=new_secret_456" in result.headers.get("location", "")

    async def test_edit_confidential_to_public(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages(is_confidential=True)
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "",
                "grant_client_credentials": "true",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
                "allowed_origins": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert result.status_code == 303
        assert client.client_secret_hash is None
        assert client.require_pkce is True

    async def test_edit_success(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages(is_confidential=True)
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "https://example.com/cb",
                "grant_client_credentials": "true",
                "is_confidential": "true",
                "require_pkce": "true",
                "require_consent": "true",
                "scope_openid": "true",
                "access_token_expiry_seconds": "7200",
                "refresh_token_expiry_seconds": "172800",
                "allowed_origins": "https://example.com",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert result.status_code == 303
        assert "success=Client+updated+successfully" in result.headers.get("location", "")

    async def test_edit_handles_exception(self):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        client = _make_client_for_pages(is_confidential=True)
        form_data = _make_form_data(
            {
                "name": "Updated",
                "redirect_uris": "",
                "grant_client_credentials": "true",
                "is_confidential": "true",
                "access_token_expiry_seconds": "",
                "refresh_token_expiry_seconds": "",
                "allowed_origins": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        db.commit = AsyncMock(side_effect=Exception("commit error"))
        auth = _make_auth()

        result = await client_edit_submit(
            request=request, client_id=str(client.id), db=db, auth=auth
        )
        assert "error=" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_disable_submit / client_enable_submit
# ---------------------------------------------------------------------------


class TestClientDisableSubmit:
    async def test_disable_success(self):
        from auth.api.routes.admin.clients_pages import client_disable_submit

        client = _make_client_for_pages(is_active=True)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_disable_submit(client_id=str(client.id), db=db, auth=auth)
        assert result.status_code == 303
        assert client.is_active is False
        assert "disabled+successfully" in result.headers.get("location", "")

    async def test_disable_not_found(self):
        from auth.api.routes.admin.clients_pages import client_disable_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_disable_submit(client_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Client+not+found" in result.headers.get("location", "")

    async def test_disable_non_uuid_id(self):
        from auth.api.routes.admin.clients_pages import client_disable_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_disable_submit(client_id="not-a-uuid", db=db, auth=auth)
        assert result.status_code == 303


class TestClientEnableSubmit:
    async def test_enable_success(self):
        from auth.api.routes.admin.clients_pages import client_enable_submit

        client = _make_client_for_pages(is_active=False)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_enable_submit(client_id=str(client.id), db=db, auth=auth)
        assert result.status_code == 303
        assert client.is_active is True
        assert "enabled+successfully" in result.headers.get("location", "")

    async def test_enable_not_found(self):
        from auth.api.routes.admin.clients_pages import client_enable_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_enable_submit(client_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Client+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_rotate_secret_submit
# ---------------------------------------------------------------------------


class TestClientRotateSecretSubmit:
    @patch(f"{CLIENTS_PAGES}.hash_password", return_value="hashed_rotated")
    @patch(f"{CLIENTS_PAGES}.generate_client_secret", return_value="rotated_secret_789")
    async def test_rotate_success(self, mock_gen, mock_hash):
        from auth.api.routes.admin.clients_pages import client_rotate_secret_submit

        client = _make_client_for_pages(is_confidential=True)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_rotate_secret_submit(client_id=str(client.id), db=db, auth=auth)
        assert result.status_code == 303
        assert "new_secret=rotated_secret_789" in result.headers.get("location", "")

    async def test_rotate_public_client_error(self):
        from auth.api.routes.admin.clients_pages import client_rotate_secret_submit

        client = _make_client_for_pages(is_confidential=False)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_rotate_secret_submit(client_id=str(client.id), db=db, auth=auth)
        assert "Cannot+rotate+secret+for+public+clients" in result.headers.get("location", "")

    async def test_rotate_not_found(self):
        from auth.api.routes.admin.clients_pages import client_rotate_secret_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_rotate_secret_submit(client_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Client+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_delete_submit
# ---------------------------------------------------------------------------


class TestClientDeleteSubmit:
    async def test_delete_success(self):
        from auth.api.routes.admin.clients_pages import client_delete_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_delete_submit(client_id=str(client.id), db=db, auth=auth)
        assert result.status_code == 303
        assert "deleted+successfully" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(client)

    async def test_delete_not_found(self):
        from auth.api.routes.admin.clients_pages import client_delete_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_delete_submit(client_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Client+not+found" in result.headers.get("location", "")

    async def test_delete_non_uuid_id(self):
        from auth.api.routes.admin.clients_pages import client_delete_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=client))
        auth = _make_auth()

        result = await client_delete_submit(client_id="non-uuid-string", db=db, auth=auth)
        assert result.status_code == 303


# ---------------------------------------------------------------------------
# client_token_revoke_submit
# ---------------------------------------------------------------------------


class TestClientTokenRevokeSubmit:
    async def test_revoke_success(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        client = _make_client_for_pages()
        token = make_access_token(client_id=client.id)
        token.revoked_at = None
        rt = make_refresh_token(access_token_id=token.id)
        rt.revoked_at = None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),  # client lookup
                make_execute_result(scalar_value=token),  # token lookup
                make_execute_result(scalars_list=[rt]),  # refresh tokens
            ]
        )
        auth = _make_auth()

        result = await client_token_revoke_submit(
            client_id=str(client.id),
            token_id=str(token.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert "Token+revoked+successfully" in result.headers.get("location", "")
        assert token.revoked_at is not None
        assert rt.revoked_at is not None

    async def test_revoke_client_not_found(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_token_revoke_submit(
            client_id=str(uuid.uuid4()),
            token_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Client+not+found" in result.headers.get("location", "")

    async def test_revoke_token_not_found(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalar_value=None),
            ]
        )
        auth = _make_auth()

        result = await client_token_revoke_submit(
            client_id=str(client.id),
            token_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Token+not+found" in result.headers.get("location", "")

    async def test_revoke_already_revoked(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        client = _make_client_for_pages()
        token = make_access_token(client_id=client.id, revoked_at=_now())

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalar_value=token),
            ]
        )
        auth = _make_auth()

        result = await client_token_revoke_submit(
            client_id=str(client.id),
            token_id=str(token.id),
            db=db,
            auth=auth,
        )
        assert "Token+already+revoked" in result.headers.get("location", "")

    async def test_revoke_invalid_token_id(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
            ]
        )
        auth = _make_auth()

        result = await client_token_revoke_submit(
            client_id=str(client.id),
            token_id="not-a-uuid",
            db=db,
            auth=auth,
        )
        assert "Invalid+token+ID" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_tokens_revoke_all_submit
# ---------------------------------------------------------------------------


class TestClientTokensRevokeAllSubmit:
    async def test_revoke_all_success(self):
        from auth.api.routes.admin.clients_pages import client_tokens_revoke_all_submit

        client = _make_client_for_pages()
        token1 = make_access_token(client_id=client.id)
        token1.revoked_at = None
        token2 = make_access_token(client_id=client.id)
        token2.revoked_at = None

        rt = make_refresh_token(client_id=client.id)
        rt.revoked_at = None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalars_list=[token1, token2]),
                make_execute_result(scalars_list=[rt]),
            ]
        )
        auth = _make_auth()

        result = await client_tokens_revoke_all_submit(client_id=str(client.id), db=db, auth=auth)
        assert result.status_code == 303
        assert "Revoked+2+token" in result.headers.get("location", "")
        assert token1.revoked_at is not None
        assert token2.revoked_at is not None
        assert rt.revoked_at is not None

    async def test_revoke_all_client_not_found(self):
        from auth.api.routes.admin.clients_pages import client_tokens_revoke_all_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await client_tokens_revoke_all_submit(
            client_id=str(uuid.uuid4()), db=db, auth=auth
        )
        assert "Client+not+found" in result.headers.get("location", "")

    async def test_revoke_all_no_tokens(self):
        from auth.api.routes.admin.clients_pages import client_tokens_revoke_all_submit

        client = _make_client_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=client),
                make_execute_result(scalars_list=[]),
                make_execute_result(scalars_list=[]),
            ]
        )
        auth = _make_auth()

        result = await client_tokens_revoke_all_submit(client_id=str(client.id), db=db, auth=auth)
        assert "Revoked+0+token" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# client_tokens_page
# ---------------------------------------------------------------------------


class TestClientTokensPage:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_tokens_page_client_not_found(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_tokens_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await client_tokens_page(
                request=request,
                client_id=str(uuid.uuid4()),
                db=db,
                auth=auth,
                page=1,
                status_filter=None,
                user_search=None,
                scope_filter=None,
            )
        assert exc_info.value.status_code == 404


# ===========================================================================
# TENANTS PAGES TESTS
# ===========================================================================


# ---------------------------------------------------------------------------
# tenant_to_dict
# ---------------------------------------------------------------------------


class TestTenantToDict:
    def test_converts_all_fields(self):
        from auth.api.routes.admin.tenants_pages import tenant_to_dict

        tenant = _make_tenant_for_pages()
        # Mock sqlalchemy inspect
        with patch("sqlalchemy.inspect") as mock_insp_fn:
            insp = MagicMock()
            insp.unloaded = set()  # All relationships loaded
            mock_insp_fn.return_value = insp

            result = tenant_to_dict(tenant)

        assert result["id"] == str(tenant.id)
        assert result["slug"] == "acme"
        assert result["display_name"] == "Acme Corp"
        assert result["is_active"] is True
        assert result["is_platform"] is False

    def test_members_unloaded(self):
        from auth.api.routes.admin.tenants_pages import tenant_to_dict

        tenant = _make_tenant_for_pages()
        with patch("sqlalchemy.inspect") as mock_insp_fn:
            insp = MagicMock()
            insp.unloaded = {"members"}
            mock_insp_fn.return_value = insp

            result = tenant_to_dict(tenant)

        assert result["members_count"] == 0

    def test_members_loaded_with_data(self):
        from auth.api.routes.admin.tenants_pages import tenant_to_dict

        member = _make_member()
        tenant = _make_tenant_for_pages(members=[member])
        with patch("sqlalchemy.inspect") as mock_insp_fn:
            insp = MagicMock()
            insp.unloaded = set()
            mock_insp_fn.return_value = insp

            result = tenant_to_dict(tenant)

        assert result["members_count"] == 1

    def test_idp_unloaded(self):
        from auth.api.routes.admin.tenants_pages import tenant_to_dict

        tenant = _make_tenant_for_pages()
        with patch("sqlalchemy.inspect") as mock_insp_fn:
            insp = MagicMock()
            insp.unloaded = {"identity_providers"}
            mock_insp_fn.return_value = insp

            result = tenant_to_dict(tenant)

        assert result["idp_count"] == 0

    def test_none_timestamps(self):
        from auth.api.routes.admin.tenants_pages import tenant_to_dict

        tenant = _make_tenant_for_pages()
        tenant.created_at = None
        tenant.updated_at = None
        with patch("sqlalchemy.inspect") as mock_insp_fn:
            insp = MagicMock()
            insp.unloaded = set()
            mock_insp_fn.return_value = insp

            result = tenant_to_dict(tenant)

        assert result["created_at"] is None
        assert result["updated_at"] is None


# ---------------------------------------------------------------------------
# member_to_dict
# ---------------------------------------------------------------------------


class TestMemberToDict:
    def test_converts_all_fields(self):
        from auth.api.routes.admin.tenants_pages import member_to_dict

        member = _make_member(role_name="admin", role_display_name="Admin")
        result = member_to_dict(member, user_email="admin@test.com")

        assert result["user_email"] == "admin@test.com"
        assert result["role"] == "admin"
        assert result["user_name"] == "Test User"

    def test_no_profile(self):
        from auth.api.routes.admin.tenants_pages import member_to_dict

        member = _make_member()
        member.user = None
        result = member_to_dict(member)

        assert result["user_name"] is None


# ---------------------------------------------------------------------------
# idp_to_dict
# ---------------------------------------------------------------------------


class TestIdpToDict:
    def test_converts_all_fields(self):
        from auth.api.routes.admin.tenants_pages import idp_to_dict

        idp = _make_idp()
        result = idp_to_dict(idp)

        assert result["name"] == "Google SSO"
        assert result["is_active"] is True
        assert result["scopes"] == ["openid", "profile", "email"]

    def test_federated_count(self):
        from auth.api.routes.admin.tenants_pages import idp_to_dict

        idp = _make_idp()
        idp.federated_identities = [MagicMock(), MagicMock()]
        result = idp_to_dict(idp)

        assert result["federated_count"] == 2


# ---------------------------------------------------------------------------
# tenants_list_page
# ---------------------------------------------------------------------------


class TestTenantsListPage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_returns_template_response(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenants_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_execute_result(scalars_list=[tenant]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id), "slug": "acme"}
            await tenants_list_page(request=request, db=db, auth=auth, page=1, search=None)

        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["active_section"] == "tenants"
        assert ctx["total"] == 1

    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_with_search(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenants_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_execute_result(scalars_list=[]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict"):
            await tenants_list_page(request=request, db=db, auth=auth, page=1, search="acme")

        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["search"] == "acme"

    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_pagination(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenants_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=50),
                make_execute_result(scalars_list=[]),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict"):
            await tenants_list_page(request=request, db=db, auth=auth, page=3, search=None)

        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total_pages"] == 3  # ceil(50/20)
        assert ctx["page"] == 3


# ---------------------------------------------------------------------------
# tenant_create_page
# ---------------------------------------------------------------------------


class TestTenantCreatePage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_returns_create_form(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_create_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        request = _mock_request(query_params={"error": "something"})
        db = AsyncMock()
        auth = _make_auth()

        await tenant_create_page(request=request, db=db, auth=auth)
        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["error"] == "something"


# ---------------------------------------------------------------------------
# tenant_create_submit
# ---------------------------------------------------------------------------


class TestTenantCreateSubmit:
    async def test_empty_slug_redirects_error(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data({"slug": "", "display_name": "Test"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert result.status_code == 303
        assert "Slug+is+required" in result.headers.get("location", "")

    async def test_empty_display_name_redirects_error(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data({"slug": "test-org", "display_name": ""})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert result.status_code == 303
        assert "Display+name+is+required" in result.headers.get("location", "")

    async def test_invalid_slug_format(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data({"slug": "-invalid-", "display_name": "Test"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert result.status_code == 303
        assert "lowercase+letters" in result.headers.get("location", "")

    async def test_duplicate_slug(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        existing = _make_tenant_for_pages(slug="acme")
        form_data = _make_form_data(
            {
                "slug": "acme",
                "display_name": "Another Acme",
                "custom_domain": "",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=existing))
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert "already+exists" in result.headers.get("location", "")

    async def test_create_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data(
            {
                "slug": "neworg",
                "display_name": "New Org",
                "custom_domain": "",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db.refresh = _refresh
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert result.status_code == 303
        assert "success=Tenant+created+successfully" in result.headers.get("location", "")

    async def test_create_seeds_the_default_roles(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data(
            {
                "slug": "neworg",
                "display_name": "New Org",
                "custom_domain": "",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db.refresh = _refresh

        with patch(
            "auth.services.tenant.tenant_role_service.create_default_roles", new=AsyncMock()
        ) as create_default_roles:
            await tenant_create_submit(request=request, db=db, auth=_make_auth())

        create_default_roles.assert_awaited_once()
        assert create_default_roles.await_args.args[1].slug == "neworg"

    async def test_create_handles_exception(self):
        from auth.api.routes.admin.tenants_pages import tenant_create_submit

        form_data = _make_form_data(
            {
                "slug": "neworg",
                "display_name": "New Org",
                "custom_domain": "",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        db.commit = AsyncMock(side_effect=Exception("DB error"))
        auth = _make_auth()

        result = await tenant_create_submit(request=request, db=db, auth=auth)
        assert "error=" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_detail_page
# ---------------------------------------------------------------------------


class TestTenantDetailPage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_tenant_found(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        role = _make_custom_role(name="member", display_order=0)
        tenant = _make_tenant_for_pages(members=[], identity_providers=[], roles=[role])

        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(
            return_value={
                "trust_mode": "none",
                "trusted_sources": [],
            }
        )
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id), "slug": "acme"}
            await tenant_detail_page(
                request=request,
                tenant_id=str(tenant.id),
                db=db,
                auth=auth,
                trust_service=trust_service,
            )

        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["active_section"] == "tenants"

    @patch(f"{TENANTS_PAGES}.app_settings")
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_access_urls_use_the_configured_base_domain(
        self, mock_get_tpl, mock_perms, mock_settings
    ):
        from auth.api.routes.admin.tenants_pages import tenant_detail_page

        mock_settings.tenant_base_domain = "auth.example.test"
        templates = _mock_templates()
        mock_get_tpl.return_value = templates
        tenant = _make_tenant_for_pages(roles=[])
        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        with patch(f"{TENANTS_PAGES}.tenant_to_dict", return_value={"id": "x", "slug": "acme"}):
            await tenant_detail_page(
                request=_mock_request(query_params={}),
                tenant_id=str(tenant.id),
                db=db,
                auth=_make_auth(),
                trust_service=trust_service,
            )

        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["tenant_base_domain"] == "auth.example.test"

    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_tenant_not_found_raises_404(self, mock_get_tpl):
        from auth.api.routes.admin.tenants_pages import tenant_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        trust_service = AsyncMock()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await tenant_detail_page(
                request=request,
                tenant_id=str(uuid.uuid4()),
                db=db,
                auth=auth,
                trust_service=trust_service,
            )
        assert exc_info.value.status_code == 404

    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_tenant_found_by_slug(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages(roles=[])

        trust_service = AsyncMock()
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)
        trust_service.get_available_tenants_for_trust = AsyncMock(return_value=[])

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id), "slug": "acme"}
            await tenant_detail_page(
                request=request,
                tenant_id="not-a-uuid",
                db=db,
                auth=auth,
                trust_service=trust_service,
            )

        templates.TemplateResponse.assert_called_once()


# ---------------------------------------------------------------------------
# tenant_edit_page
# ---------------------------------------------------------------------------


class TestTenantEditPage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_edit_page_found(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id)}
            await tenant_edit_page(request=request, tenant_id=str(tenant.id), db=db, auth=auth)

        templates.TemplateResponse.assert_called_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert "tenant_base_domain" in ctx

    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_edit_page_not_found(self, mock_get_tpl):
        from auth.api.routes.admin.tenants_pages import tenant_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await tenant_edit_page(request=request, tenant_id=str(uuid.uuid4()), db=db, auth=auth)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# tenant_edit_submit
# ---------------------------------------------------------------------------


class TestTenantEditSubmit:
    async def test_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_edit_submit

        form_data = _make_form_data({"display_name": "Updated"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_edit_submit(
            request=request, tenant_id=str(uuid.uuid4()), db=db, auth=auth
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_empty_display_name(self):
        from auth.api.routes.admin.tenants_pages import tenant_edit_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data({"display_name": "", "custom_domain": ""})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_edit_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "Display+name+is+required" in result.headers.get("location", "")

    async def test_edit_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_edit_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data(
            {
                "display_name": "Updated Corp",
                "custom_domain": "auth.updated.com",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_edit_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert result.status_code == 303
        assert "success=Tenant+updated+successfully" in result.headers.get("location", "")
        assert tenant.display_name == "Updated Corp"

    async def test_edit_handles_exception(self):
        from auth.api.routes.admin.tenants_pages import tenant_edit_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data(
            {
                "display_name": "Updated",
                "custom_domain": "",
                "is_active": "true",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        db.commit = AsyncMock(side_effect=Exception("commit error"))
        auth = _make_auth()

        result = await tenant_edit_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "error=" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_disable_submit / tenant_enable_submit
# ---------------------------------------------------------------------------


class TestTenantDisableSubmit:
    async def test_disable_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_disable_submit

        tenant = _make_tenant_for_pages(is_active=True)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_disable_submit(tenant_id=str(tenant.id), db=db, auth=auth)
        assert result.status_code == 303
        assert tenant.is_active is False

    async def test_disable_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_disable_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_disable_submit(tenant_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Tenant+not+found" in result.headers.get("location", "")


class TestTenantEnableSubmit:
    async def test_enable_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_enable_submit

        tenant = _make_tenant_for_pages(is_active=False)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_enable_submit(tenant_id=str(tenant.id), db=db, auth=auth)
        assert result.status_code == 303
        assert tenant.is_active is True

    async def test_enable_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_enable_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_enable_submit(tenant_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Tenant+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_delete_submit
# ---------------------------------------------------------------------------


class TestTenantDeleteSubmit:
    async def test_delete_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_delete_submit

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_delete_submit(tenant_id=str(tenant.id), db=db, auth=auth)
        assert result.status_code == 303
        assert "deleted+successfully" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(tenant)

    async def test_delete_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_delete_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_delete_submit(tenant_id=str(uuid.uuid4()), db=db, auth=auth)
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_delete_by_slug(self):
        from auth.api.routes.admin.tenants_pages import tenant_delete_submit

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_delete_submit(tenant_id="not-a-uuid-slug", db=db, auth=auth)
        assert result.status_code == 303


# ---------------------------------------------------------------------------
# tenant_add_member_submit
# ---------------------------------------------------------------------------


class TestTenantAddMemberSubmit:
    async def test_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        form_data = _make_form_data({"email": "user@test.com", "role": "member"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(uuid.uuid4()), db=db, auth=auth
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_empty_email(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data({"email": "", "role": "member"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "Email+is+required" in result.headers.get("location", "")

    async def test_user_not_found_by_email(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        tenant = _make_tenant_for_pages()
        role = _make_custom_role()
        form_data = _make_form_data({"email": "unknown@test.com", "role": "member"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),  # tenant lookup
                make_execute_result(scalar_value=role),  # role lookup
                make_execute_result(scalar_value=None),  # user email lookup
            ]
        )
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "User+not+found" in result.headers.get("location", "")

    async def test_already_a_member(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        tenant = _make_tenant_for_pages()
        role = _make_custom_role()
        user_email_obj = MagicMock()
        user_email_obj.user_id = uuid.uuid4()
        existing_member = _make_member(user_id=user_email_obj.user_id)

        form_data = _make_form_data({"email": "existing@test.com", "role": "member"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=role),
                make_execute_result(scalar_value=user_email_obj),
                make_execute_result(scalar_value=existing_member),
            ]
        )
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "already+a+member" in result.headers.get("location", "")

    async def test_add_member_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        tenant = _make_tenant_for_pages()
        role = _make_custom_role()
        user_email_obj = MagicMock()
        user_email_obj.user_id = uuid.uuid4()

        form_data = _make_form_data({"email": "new@test.com", "role": "member"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=role),
                make_execute_result(scalar_value=user_email_obj),
                make_execute_result(scalar_value=None),  # no existing membership
            ]
        )
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert result.status_code == 303
        assert "Member+added+successfully" in result.headers.get("location", "")

    async def test_role_not_found_fallback_to_member(self):
        from auth.api.routes.admin.tenants_pages import tenant_add_member_submit

        tenant = _make_tenant_for_pages()
        user_email_obj = MagicMock()
        user_email_obj.user_id = uuid.uuid4()

        form_data = _make_form_data({"email": "new@test.com", "role": "nonexistent"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()

        # Role lookup fails first time, then falls back to "member" which also fails
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=None),  # role "nonexistent" not found
                make_execute_result(scalar_value=None),  # fallback "member" not found
            ]
        )
        auth = _make_auth()

        result = await tenant_add_member_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "Role+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_update_member_role_submit
# ---------------------------------------------------------------------------


class TestTenantUpdateMemberRoleSubmit:
    async def test_member_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_update_member_role_submit

        form_data = _make_form_data({"role": "admin"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_update_member_role_submit(
            request=request,
            tenant_id=str(uuid.uuid4()),
            member_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Member+not+found" in result.headers.get("location", "")

    async def test_invalid_member_id(self):
        from auth.api.routes.admin.tenants_pages import tenant_update_member_role_submit

        form_data = _make_form_data({"role": "admin"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        auth = _make_auth()

        result = await tenant_update_member_role_submit(
            request=request,
            tenant_id=str(uuid.uuid4()),
            member_id="not-a-uuid",
            db=db,
            auth=auth,
        )
        assert "Invalid+member+ID" in result.headers.get("location", "")

    async def test_update_role_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_update_member_role_submit

        member = _make_member()
        role = _make_custom_role(name="admin", display_name="Admin")

        form_data = _make_form_data({"role": "admin"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=member),
                make_execute_result(scalar_value=role),
            ]
        )
        auth = _make_auth()

        result = await tenant_update_member_role_submit(
            request=request,
            tenant_id=str(uuid.uuid4()),
            member_id=str(member.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert "Member+role+updated" in result.headers.get("location", "")

    async def test_role_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_update_member_role_submit

        member = _make_member()
        form_data = _make_form_data({"role": "nonexistent"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=member),
                make_execute_result(scalar_value=None),
            ]
        )
        auth = _make_auth()

        result = await tenant_update_member_role_submit(
            request=request,
            tenant_id=str(uuid.uuid4()),
            member_id=str(member.id),
            db=db,
            auth=auth,
        )
        assert "Role+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_remove_member_submit
# ---------------------------------------------------------------------------


class TestTenantRemoveMemberSubmit:
    async def test_remove_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_remove_member_submit

        member = _make_member()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))
        auth = _make_auth()

        result = await tenant_remove_member_submit(
            tenant_id=str(uuid.uuid4()),
            member_id=str(member.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert "Member+removed" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(member)

    async def test_remove_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_remove_member_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_remove_member_submit(
            tenant_id=str(uuid.uuid4()),
            member_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Member+not+found" in result.headers.get("location", "")

    async def test_remove_invalid_id(self):
        from auth.api.routes.admin.tenants_pages import tenant_remove_member_submit

        db = AsyncMock()
        auth = _make_auth()

        result = await tenant_remove_member_submit(
            tenant_id=str(uuid.uuid4()),
            member_id="not-a-uuid",
            db=db,
            auth=auth,
        )
        assert "Invalid+member+ID" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_idp_create_page
# ---------------------------------------------------------------------------


class TestTenantIdpCreatePage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_idp_create_page_found(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id)}
            await tenant_idp_create_page(
                request=request,
                tenant_id=str(tenant.id),
                db=db,
                auth=auth,
            )

        templates.TemplateResponse.assert_called_once()

    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_idp_create_page_tenant_not_found(self, mock_get_tpl):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await tenant_idp_create_page(
                request=request,
                tenant_id=str(uuid.uuid4()),
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# tenant_idp_create_submit
# ---------------------------------------------------------------------------


class TestTenantIdpCreateSubmit:
    async def test_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit

        form_data = _make_form_data({"name": "IdP", "client_id": "cid"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_idp_create_submit(
            request=request, tenant_id=str(uuid.uuid4()), db=db, auth=auth
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_missing_name_and_client_id(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data({"name": "", "client_id": ""})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        auth = _make_auth()

        result = await tenant_idp_create_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert "Name+and+Client+ID+are+required" in result.headers.get("location", "")

    @patch(f"{TENANTS_PAGES}.get_encryption")
    async def test_create_idp_success(self, mock_encryption):
        from auth.api.routes.admin.tenants_pages import tenant_idp_create_submit

        enc = MagicMock()
        enc.encrypt.return_value = b"encrypted_secret"
        mock_encryption.return_value = enc

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data(
            {
                "name": "Google SSO",
                "provider_type": "oidc",
                "client_id": "google-client-id",
                "client_secret": "google-secret",
                "discovery_url": "https://accounts.google.com",
                "scopes": "openid profile email",
                "is_active": "true",
                "is_default": "true",
                "auto_provision": "true",
                "allow_linking": "true",
                "button_text": "Sign in with Google",
                "icon_url": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        async def _refresh(obj):
            obj.id = uuid.uuid4()

        db.refresh = _refresh
        auth = _make_auth()

        result = await tenant_idp_create_submit(
            request=request, tenant_id=str(tenant.id), db=db, auth=auth
        )
        assert result.status_code == 303
        assert "Identity+provider+created+successfully" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_idp_edit_page
# ---------------------------------------------------------------------------


class TestTenantIdpEditPage:
    @patch(f"{TENANTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_edit_page_found(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )

        request = _mock_request(query_params={})
        auth = _make_auth()

        with patch(f"{TENANTS_PAGES}.tenant_to_dict") as mock_to_dict:
            mock_to_dict.return_value = {"id": str(tenant.id)}
            await tenant_idp_edit_page(
                request=request,
                tenant_id=str(tenant.id),
                idp_id=str(idp.id),
                db=db,
                auth=auth,
            )

        templates.TemplateResponse.assert_called_once()

    @patch(f"{TENANTS_PAGES}.get_templates")
    async def test_invalid_idp_id(self, mock_get_tpl):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))
        request = _mock_request()
        auth = _make_auth()

        with pytest.raises(HTTPException) as exc_info:
            await tenant_idp_edit_page(
                request=request,
                tenant_id=str(tenant.id),
                idp_id="not-a-uuid",
                db=db,
                auth=auth,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# tenant_idp_edit_submit
# ---------------------------------------------------------------------------


class TestTenantIdpEditSubmit:
    async def test_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        form_data = _make_form_data({"name": "Updated", "client_id": "cid"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_idp_edit_submit(
            request=request,
            tenant_id=str(uuid.uuid4()),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_idp_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        tenant = _make_tenant_for_pages()
        form_data = _make_form_data({"name": "Updated", "client_id": "cid"})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=None),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_edit_submit(
            request=request,
            tenant_id=str(tenant.id),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Identity+provider+not+found" in result.headers.get("location", "")

    async def test_missing_name_redirects(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id)
        form_data = _make_form_data({"name": "", "client_id": ""})
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_edit_submit(
            request=request,
            tenant_id=str(tenant.id),
            idp_id=str(idp.id),
            db=db,
            auth=auth,
        )
        assert "Name+and+Client+ID+are+required" in result.headers.get("location", "")

    @patch(f"{TENANTS_PAGES}.get_encryption")
    async def test_edit_idp_success_with_new_secret(self, mock_encryption):
        from auth.api.routes.admin.tenants_pages import tenant_idp_edit_submit

        enc = MagicMock()
        enc.encrypt.return_value = b"new_encrypted"
        mock_encryption.return_value = enc

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id)
        form_data = _make_form_data(
            {
                "name": "Updated SSO",
                "client_id": "updated-cid",
                "client_secret": "new-secret",
                "discovery_url": "https://updated.com",
                "scopes": "openid profile",
                "is_active": "true",
                "is_default": "",
                "auto_provision": "true",
                "allow_linking": "",
                "button_text": "Sign in",
                "icon_url": "",
            }
        )
        request = _mock_request(form_data=form_data)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_edit_submit(
            request=request,
            tenant_id=str(tenant.id),
            idp_id=str(idp.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert "Identity+provider+updated+successfully" in result.headers.get("location", "")
        assert idp.name == "Updated SSO"


# ---------------------------------------------------------------------------
# tenant_idp_delete_submit
# ---------------------------------------------------------------------------


class TestTenantIdpDeleteSubmit:
    async def test_delete_success(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_delete_submit

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_delete_submit(
            tenant_id=str(tenant.id),
            idp_id=str(idp.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert "Identity+provider+deleted" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(idp)

    async def test_delete_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_delete_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_idp_delete_submit(
            tenant_id=str(uuid.uuid4()),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_delete_idp_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_delete_submit

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=None),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_delete_submit(
            tenant_id=str(tenant.id),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Identity+provider+not+found" in result.headers.get("location", "")

    async def test_delete_invalid_idp_id(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_delete_submit

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_delete_submit(
            tenant_id=str(tenant.id),
            idp_id="not-a-uuid",
            db=db,
            auth=auth,
        )
        assert "Invalid+IdP+ID" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# tenant_idp_toggle_submit
# ---------------------------------------------------------------------------


class TestTenantIdpToggleSubmit:
    async def test_toggle_enable(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_toggle_submit

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id, is_active=False)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_toggle_submit(
            tenant_id=str(tenant.id),
            idp_id=str(idp.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert idp.is_active is True
        assert "enabled" in result.headers.get("location", "")

    async def test_toggle_disable(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_toggle_submit

        tenant = _make_tenant_for_pages()
        idp = _make_idp(tenant_id=tenant.id, is_active=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=idp),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_toggle_submit(
            tenant_id=str(tenant.id),
            idp_id=str(idp.id),
            db=db,
            auth=auth,
        )
        assert result.status_code == 303
        assert idp.is_active is False

    async def test_toggle_tenant_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_toggle_submit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        auth = _make_auth()

        result = await tenant_idp_toggle_submit(
            tenant_id=str(uuid.uuid4()),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Tenant+not+found" in result.headers.get("location", "")

    async def test_toggle_idp_not_found(self):
        from auth.api.routes.admin.tenants_pages import tenant_idp_toggle_submit

        tenant = _make_tenant_for_pages()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=tenant),
                make_execute_result(scalar_value=None),
            ]
        )
        auth = _make_auth()

        result = await tenant_idp_toggle_submit(
            tenant_id=str(tenant.id),
            idp_id=str(uuid.uuid4()),
            db=db,
            auth=auth,
        )
        assert "Identity+provider+not+found" in result.headers.get("location", "")


# ---------------------------------------------------------------------------
# OIDC_SCOPES and SYSTEM_SCOPES constants
# ---------------------------------------------------------------------------


class TestScopeConstants:
    def test_oidc_scopes_present(self):
        from auth.api.routes.admin.clients_pages import OIDC_SCOPES

        names = [s["name"] for s in OIDC_SCOPES]
        assert "openid" in names
        assert "profile" in names
        assert "email" in names
        assert "offline_access" in names

    def test_system_scopes_present(self):
        from auth.api.routes.admin.clients_pages import SYSTEM_SCOPES

        names = [s["name"] for s in SYSTEM_SCOPES]
        assert "introspect" in names


# ---------------------------------------------------------------------------
# branding_to_dict
# ---------------------------------------------------------------------------


class TestBrandingToDict:
    def test_none_returns_none(self):
        from auth.api.routes.admin.tenants_pages import branding_to_dict

        assert branding_to_dict(None) is None

    def test_converts_branding(self):
        from auth.api.routes.admin.tenants_pages import branding_to_dict

        branding = MagicMock()
        branding.id = uuid.uuid4()
        branding.tenant_id = uuid.uuid4()
        branding.logo_url = "https://example.com/logo.png"
        branding.logo_dark_url = None
        branding.favicon_url = None
        branding.primary_color = "#007bff"
        branding.secondary_color = "#6c757d"
        branding.accent_color = "#28a745"
        branding.background_color = "#f5f5f5"
        branding.surface_color = "#ffffff"
        branding.text_color = "#333333"
        branding.text_muted_color = "#6c757d"
        branding.error_color = "#dc3545"
        branding.success_color = "#28a745"
        branding.border_color = "#0f3460"
        branding.warning_color = "#fdcb6e"
        branding.info_color = "#74b9ff"
        branding.font_family = "sans-serif"
        branding.font_url = None
        branding.custom_css = None
        branding.custom_js = None
        branding.show_powered_by = True
        branding.created_at = _now()
        branding.updated_at = _now()

        result = branding_to_dict(branding)
        assert result["logo_url"] == "https://example.com/logo.png"
        assert result["primary_color"] == "#007bff"
        assert result["show_powered_by"] is True


# ---------------------------------------------------------------------------
# template_to_dict
# ---------------------------------------------------------------------------


class TestTemplateToDict:
    def test_converts_template(self):
        from auth.api.routes.admin.tenants_pages import template_to_dict

        tmpl = MagicMock()
        tmpl.id = uuid.uuid4()
        tmpl.tenant_id = uuid.uuid4()
        tmpl.template_name = "login.html"
        tmpl.content = "<html></html>"
        tmpl.is_active = True
        tmpl.description = "Login page"
        tmpl.created_at = _now()
        tmpl.updated_at = _now()

        result = template_to_dict(tmpl)
        assert result["template_name"] == "login.html"
        assert result["content"] == "<html></html>"
        assert result["is_active"] is True


# ===========================================================================
# clients_pages — remaining branches
# ===========================================================================


class TestClientsListPageTenantFilter:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_global_filter_excludes_tenant_clients(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.list", AsyncMock(return_value=([], 0))
            ) as list_clients,
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(return_value=[]),
            ),
        ):
            await clients_list_page(
                request=_mock_request(query_params={}),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                search=None,
                tenant_filter="global",
            )

        assert list_clients.await_args.kwargs["filter_no_tenant"] is True

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_uuid_filter_is_parsed(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates
        tenant_id = uuid.uuid4()

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.list", AsyncMock(return_value=([], 0))
            ) as list_clients,
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(return_value=[]),
            ),
        ):
            await clients_list_page(
                request=_mock_request(query_params={}),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                search=None,
                tenant_filter=str(tenant_id),
            )

        assert list_clients.await_args.kwargs["tenant_id"] == tenant_id

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_tenant_names_are_resolved_for_scoped_clients(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        tenant_id = uuid.uuid4()
        client = _make_client_for_pages()
        client.tenant_id = tenant_id

        with (
            patch(f"{CLIENTS_PAGES}._client_service.list", AsyncMock(return_value=([client], 1))),
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(side_effect=[[(tenant_id, "Acme")], []]),
            ),
        ):
            await clients_list_page(
                request=_mock_request(query_params={}),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                search=None,
                tenant_filter=None,
            )

        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["clients"][0]["tenant_name"] == "Acme"


_ALL_GRANT_FIELDS = {
    "grant_authorization_code": "true",
    "grant_refresh_token": "true",
    "grant_client_credentials": "true",
    "grant_device_code": "true",
    "grant_token_exchange": "true",
    "grant_password": "true",
}


class TestClientSubmitGrantTypes:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_create_collects_every_grant_type(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_create_submit

        mock_get_tpl.return_value = _mock_templates()

        form = {
            "name": "My App",
            "redirect_uris": "https://app.example.com/cb",
            "allowed_scopes": "openid",
            **_ALL_GRANT_FIELDS,
        }
        request = _mock_request(form_data=form)

        staged = {}

        async def _add(_db, client):
            staged["client"] = client
            client.id = uuid.uuid4()

        with patch(f"{CLIENTS_PAGES}._client_service.add", AsyncMock(side_effect=_add)):
            result = await client_create_submit(request=request, db=AsyncMock(), auth=_make_auth())

        assert result.status_code == 303
        assert set(staged["client"].allowed_grant_types) == {
            "authorization_code",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:device_code",
            "urn:ietf:params:oauth:grant-type:token-exchange",
            "password",
        }

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_edit_collects_every_grant_type(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_edit_submit

        mock_get_tpl.return_value = _mock_templates()

        client = _make_client_for_pages()
        form = {
            "name": "My App",
            "redirect_uris": "https://app.example.com/cb",
            "allowed_scopes": "openid",
            **_ALL_GRANT_FIELDS,
        }

        with patch(
            f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
            AsyncMock(return_value=client),
        ):
            result = await client_edit_submit(
                request=_mock_request(form_data=form),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
            )

        assert result.status_code == 303
        assert set(client.allowed_grant_types) == {
            "authorization_code",
            "refresh_token",
            "client_credentials",
            "urn:ietf:params:oauth:grant-type:device_code",
            "urn:ietf:params:oauth:grant-type:token-exchange",
            "password",
        }


class TestClientPagesTenantName:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_detail_page_resolves_tenant_name_and_user_emails(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = uuid.uuid4()

        token = MagicMock()
        token.id = uuid.uuid4()
        token.user_id = uuid.uuid4()
        token.jti = "jti"
        token.scopes = ["openid"]
        token.issued_at = _now()
        token.expires_at = _now()
        token.revoked_at = None
        token.is_expired = False

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_access_tokens_for_client",
                AsyncMock(return_value=[token]),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_access_tokens_for_client",
                AsyncMock(return_value=1),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_active_access_tokens_for_client",
                AsyncMock(return_value=1),
            ),
            patch(
                f"{CLIENTS_PAGES}._user_service.get_primary_email",
                AsyncMock(return_value="owner@example.com"),
            ) as get_email,
            patch(
                f"{CLIENTS_PAGES}._tenant_service.get_display_name",
                AsyncMock(return_value="Acme"),
            ),
        ):
            await client_detail_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
                tokens_page=1,
            )

        get_email.assert_awaited_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["client"]["tenant_name"] == "Acme"

    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_edit_page_resolves_tenant_name(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_edit_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = uuid.uuid4()

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(f"{CLIENTS_PAGES}.get_available_scopes", AsyncMock(return_value={})),
            patch(
                f"{CLIENTS_PAGES}._tenant_service.get_display_name",
                AsyncMock(return_value="Acme"),
            ),
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(return_value=[]),
            ),
        ):
            await client_edit_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
            )

        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["client"]["tenant_name"] == "Acme"


class TestClientTokensPageSuccess:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_renders_with_filters(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_tokens_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()

        token = MagicMock()
        token.id = uuid.uuid4()
        token.user_id = uuid.uuid4()
        token.jti = "jti"
        token.scopes = ["openid"]
        token.issued_at = _now()
        token.expires_at = _now()
        token.revoked_at = None
        token.is_expired = False

        anon_token = MagicMock()
        anon_token.id = uuid.uuid4()
        anon_token.user_id = None
        anon_token.jti = "jti2"
        anon_token.scopes = ["api"]
        anon_token.issued_at = _now()
        anon_token.expires_at = _now()
        anon_token.revoked_at = None
        anon_token.is_expired = False

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_user_ids_by_email_search",
                AsyncMock(return_value=[token.user_id]),
            ) as search_users,
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.search_access_tokens_for_client",
                AsyncMock(return_value=([token, anon_token], 2)),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_active_access_tokens_for_client",
                AsyncMock(return_value=2),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_revoked_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_expired_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_access_tokens_for_client",
                AsyncMock(return_value=2),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_distinct_scopes_for_client",
                AsyncMock(return_value=["openid"]),
            ),
            patch(
                f"{CLIENTS_PAGES}._user_service.get_primary_email",
                AsyncMock(return_value="owner@example.com"),
            ) as get_email,
        ):
            await client_tokens_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                status_filter="active",
                user_search="owner@",
                scope_filter="openid",
            )

        search_users.assert_awaited_once()
        get_email.assert_awaited_once()
        ctx = templates.TemplateResponse.call_args[1]["context"]
        assert ctx["total"] == 2


class TestClientTokenRevokeSkipsRevokedRefreshTokens:
    async def test_already_revoked_refresh_token_is_left_alone(self):
        from auth.api.routes.admin.clients_pages import client_token_revoke_submit

        client = _make_client_for_pages()
        token = MagicMock()
        token.id = uuid.uuid4()
        token.revoked_at = None

        already_revoked = MagicMock()
        already_revoked.revoked_at = _now()
        pending = MagicMock()
        pending.revoked_at = None

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.get_access_token_for_client",
                AsyncMock(return_value=token),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_refresh_tokens_for_access_token",
                AsyncMock(return_value=[already_revoked, pending]),
            ),
        ):
            result = await client_token_revoke_submit(
                client_id=str(client.id),
                token_id=str(token.id),
                db=AsyncMock(),
                auth=_make_auth(),
            )

        assert result.status_code == 303
        assert pending.revoked_at is not None


class TestClientsListPageInvalidTenantFilter:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_unparseable_filter_falls_back_to_no_filter(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import clients_list_page

        mock_get_tpl.return_value = _mock_templates()

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.list", AsyncMock(return_value=([], 0))
            ) as list_clients,
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(return_value=[]),
            ),
        ):
            await clients_list_page(
                request=_mock_request(query_params={}),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                search=None,
                tenant_filter="not-a-uuid",
            )

        assert list_clients.await_args.kwargs["tenant_id"] is None


class TestClientDetailPageWithoutTenant:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_client_credentials_token_has_no_user_email(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_detail_page

        templates = _mock_templates()
        mock_get_tpl.return_value = templates

        client = _make_client_for_pages()
        client.tenant_id = None

        token = MagicMock()
        token.id = uuid.uuid4()
        token.user_id = None
        token.jti = "jti"
        token.scopes = ["api"]
        token.issued_at = _now()
        token.expires_at = _now()
        token.revoked_at = None
        token.is_expired = False

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_access_tokens_for_client",
                AsyncMock(return_value=[token]),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_access_tokens_for_client",
                AsyncMock(return_value=1),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_active_access_tokens_for_client",
                AsyncMock(return_value=1),
            ),
            patch(f"{CLIENTS_PAGES}._user_service.get_primary_email", AsyncMock()) as get_email,
            patch(f"{CLIENTS_PAGES}._tenant_service.get_display_name", AsyncMock()) as get_name,
        ):
            await client_detail_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
                tokens_page=1,
            )

        get_email.assert_not_awaited()
        get_name.assert_not_awaited()


class TestClientEditPageWithoutTenant:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_global_client_skips_the_tenant_lookup(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_edit_page

        mock_get_tpl.return_value = _mock_templates()

        client = _make_client_for_pages()
        client.tenant_id = None

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(f"{CLIENTS_PAGES}.get_available_scopes", AsyncMock(return_value={})),
            patch(f"{CLIENTS_PAGES}._tenant_service.get_display_name", AsyncMock()) as get_name,
            patch(
                f"{CLIENTS_PAGES}._tenant_service.list_id_name_pairs",
                AsyncMock(return_value=[]),
            ),
        ):
            await client_edit_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
            )

        get_name.assert_not_awaited()


class TestClientTokensPageWithoutUserSearch:
    @patch(f"{CLIENTS_PAGES}.get_user_admin_permissions", return_value={})
    @patch(f"{CLIENTS_PAGES}.get_templates")
    async def test_no_user_filter_skips_the_email_lookup(self, mock_get_tpl, mock_perms):
        from auth.api.routes.admin.clients_pages import client_tokens_page

        mock_get_tpl.return_value = _mock_templates()
        client = _make_client_for_pages()

        with (
            patch(
                f"{CLIENTS_PAGES}._client_service.get_by_id_or_client_id",
                AsyncMock(return_value=client),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_user_ids_by_email_search",
                AsyncMock(),
            ) as search_users,
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.search_access_tokens_for_client",
                AsyncMock(return_value=([], 0)),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_active_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_revoked_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_expired_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.count_access_tokens_for_client",
                AsyncMock(return_value=0),
            ),
            patch(
                f"{CLIENTS_PAGES}._token_admin_service.list_distinct_scopes_for_client",
                AsyncMock(return_value=[]),
            ),
        ):
            await client_tokens_page(
                request=_mock_request(query_params={}),
                client_id=str(client.id),
                db=AsyncMock(),
                auth=_make_auth(),
                page=1,
                status_filter=None,
                user_search=None,
                scope_filter=None,
            )

        search_users.assert_not_awaited()
