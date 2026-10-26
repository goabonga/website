# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for app/routes/namespaces.py - Knowledge Namespace CRUD routes."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse
from internal.auth.models import User

USER_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_user(**kwargs):
    defaults = {
        "id": USER_UUID,
        "email": "test@example.com",
        "name": "Test",
        "scopes": ["*"],
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_request(**kwargs):
    req = MagicMock()
    req.query_params = kwargs.get("query_params", {})
    req.headers = kwargs.get("headers", {})
    req.form = AsyncMock(return_value=MagicMock())
    req.cookies = kwargs.get("cookies", {})
    return req


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()  # add() is synchronous in SQLAlchemy
    return db


def _make_namespace(**kwargs):
    ns = MagicMock()
    ns.id = kwargs.get("id", 1)
    ns.slug = kwargs.get("slug", "test-ns")
    ns.name = kwargs.get("name", "Test Namespace")
    ns.description = kwargs.get("description", "A test namespace")
    ns.required_scopes = kwargs.get("required_scopes")
    ns.is_public = kwargs.get("is_public", True)
    return ns


# =========================================================================
# ensure_default_namespace helper
# =========================================================================


class TestEnsureDefaultNamespace:
    @pytest.mark.asyncio
    async def test_namespace_exists(self):
        from internal.routes.namespaces import ensure_default_namespace

        db = _make_db()
        ns = _make_namespace(slug="general")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        result = await ensure_default_namespace(db)
        assert result is ns
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_namespace_does_not_exist(self):
        from internal.routes.namespaces import ensure_default_namespace

        db = _make_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        await ensure_default_namespace(db)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()


# =========================================================================
# Namespace List
# =========================================================================


class TestNamespaceList:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_list

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_list(request=req, page=1, search=None, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_list_success(self):
        from internal.routes.namespaces import namespace_list

        req = _make_request(query_params={"success": "OK", "error": None})
        db = _make_db()
        user = _make_user()

        # ensure_default_namespace: first execute
        ns_default = _make_namespace(slug="general")
        ensure_result = MagicMock()
        ensure_result.scalar_one_or_none.return_value = ns_default

        # scalar for count
        db.scalar = AsyncMock(return_value=2)

        # execute for paginated results
        ns1 = _make_namespace(id=1)
        ns2 = _make_namespace(id=2)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [ns1, ns2]
        paginated_result = MagicMock()
        paginated_result.scalars.return_value = scalars_mock

        db.execute = AsyncMock(side_effect=[ensure_result, paginated_result])

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_list(request=req, page=1, search=None, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 2
            assert len(call_kwargs["context"]["namespaces"]) == 2
            assert call_kwargs["context"]["success"] == "OK"

    @pytest.mark.asyncio
    async def test_list_with_search(self):
        from internal.routes.namespaces import namespace_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ns_default = _make_namespace(slug="general")
        ensure_result = MagicMock()
        ensure_result.scalar_one_or_none.return_value = ns_default

        db.scalar = AsyncMock(return_value=0)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        paginated_result = MagicMock()
        paginated_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[ensure_result, paginated_result])

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_list(request=req, page=1, search="test", db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["search"] == "test"

    @pytest.mark.asyncio
    async def test_list_null_total(self):
        from internal.routes.namespaces import namespace_list

        req = _make_request(query_params={})
        db = _make_db()
        user = _make_user()

        ensure_result = MagicMock()
        ensure_result.scalar_one_or_none.return_value = _make_namespace(slug="general")

        db.scalar = AsyncMock(return_value=None)
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        paginated_result = MagicMock()
        paginated_result.scalars.return_value = scalars_mock
        db.execute = AsyncMock(side_effect=[ensure_result, paginated_result])

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_list(request=req, page=1, search=None, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["total"] == 0
            assert call_kwargs["context"]["total_pages"] == 1


# =========================================================================
# Namespace New
# =========================================================================


class TestNamespaceNew:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_new

        req = _make_request()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_new(request=req, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_form_displayed(self):
        from internal.routes.namespaces import namespace_new

        req = _make_request()
        user = _make_user()

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_new(request=req, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["namespace"] is None
            assert call_kwargs["context"]["is_edit"] is False


# =========================================================================
# Namespace Create
# =========================================================================


class TestNamespaceCreate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_create

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_create(
            request=req,
            slug="test",
            name="Test",
            description="",
            required_scopes="",
            is_public=True,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_slug_already_exists(self):
        from internal.routes.namespaces import namespace_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        existing = _make_namespace(slug="existing")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        result = await namespace_create(
            request=req,
            slug="Existing",
            name="Test",
            description="",
            required_scopes="",
            is_public=True,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "already+exists" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_create_success(self):
        from internal.routes.namespaces import namespace_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_create(
                request=req,
                slug="  New-Ns  ",
                name="  New Namespace  ",
                description="  A description  ",
                required_scopes="scope1, scope2",
                is_public=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_no_scopes(self):
        from internal.routes.namespaces import namespace_create

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_create(
                request=req,
                slug="test-ns",
                name="Test",
                description="",
                required_scopes="",
                is_public=True,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")


# =========================================================================
# Namespace Detail
# =========================================================================


class TestNamespaceDetail:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_detail

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_detail(request=req, namespace_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.namespaces import namespace_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_detail(request=req, namespace_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_found(self):
        from internal.routes.namespaces import namespace_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns

        count_result = MagicMock()
        count_result.scalar.return_value = 5

        db.execute = AsyncMock(side_effect=[ns_result, count_result])

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_detail(request=req, namespace_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["namespace"] is ns
            assert call_kwargs["context"]["entry_count"] == 5

    @pytest.mark.asyncio
    async def test_found_null_count(self):
        from internal.routes.namespaces import namespace_detail

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace()
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns

        count_result = MagicMock()
        count_result.scalar.return_value = None

        db.execute = AsyncMock(side_effect=[ns_result, count_result])

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_detail(request=req, namespace_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["entry_count"] == 0


# =========================================================================
# Namespace Edit
# =========================================================================


class TestNamespaceEdit:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_edit

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_edit(request=req, namespace_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.namespaces import namespace_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_edit(request=req, namespace_id=999, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_found(self):
        from internal.routes.namespaces import namespace_edit

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        with (
            patch("internal.routes.namespaces.templates") as mock_templates,
            patch("internal.routes.namespaces.settings") as mock_settings,
        ):
            mock_settings.oauth2_client_id = "test-client"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await namespace_edit(request=req, namespace_id=1, db=db, auth_result=user)

            call_kwargs = mock_templates.TemplateResponse.call_args.kwargs
            assert call_kwargs["context"]["namespace"] is ns
            assert call_kwargs["context"]["is_edit"] is True


# =========================================================================
# Namespace Update
# =========================================================================


class TestNamespaceUpdate:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_update(
            request=req,
            namespace_id=1,
            slug="test",
            name="Test",
            description="",
            required_scopes="",
            is_public=True,
            db=db,
            auth_result=redirect,
        )
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await namespace_update(
            request=req,
            namespace_id=999,
            slug="test",
            name="Test",
            description="",
            required_scopes="",
            is_public=True,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_slug_conflict(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(id=1, slug="old-slug")
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns

        existing = _make_namespace(id=2, slug="new-slug")
        conflict_result = MagicMock()
        conflict_result.scalar_one_or_none.return_value = existing

        db.execute = AsyncMock(side_effect=[ns_result, conflict_result])

        result = await namespace_update(
            request=req,
            namespace_id=1,
            slug="new-slug",
            name="Updated",
            description="",
            required_scopes="",
            is_public=True,
            db=db,
            auth_result=user,
        )
        assert isinstance(result, RedirectResponse)
        assert "already+exists" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_success_same_slug(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(id=1, slug="test-ns")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_update(
                request=req,
                namespace_id=1,
                slug="test-ns",
                name="Updated Name",
                description="New desc",
                required_scopes="scope1, scope2",
                is_public=False,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert "success" in result.headers.get("location", "")
        db.commit.assert_awaited_once()
        assert ns.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_success_new_slug_no_conflict(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(id=1, slug="old-slug")
        ns_result = MagicMock()
        ns_result.scalar_one_or_none.return_value = ns

        no_conflict = MagicMock()
        no_conflict.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[ns_result, no_conflict])

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_update(
                request=req,
                namespace_id=1,
                slug="new-slug",
                name="Updated",
                description="",
                required_scopes="",
                is_public=True,
                db=db,
                auth_result=user,
            )

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_update_empty_description(self):
        from internal.routes.namespaces import namespace_update

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(id=1, slug="test-ns")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            await namespace_update(
                request=req,
                namespace_id=1,
                slug="test-ns",
                name="Test",
                description="   ",
                required_scopes="",
                is_public=True,
                db=db,
                auth_result=user,
            )

        assert ns.description is None


# =========================================================================
# Namespace Bulk Delete
# =========================================================================


class TestNamespaceBulkDelete:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_bulk_delete(request=req, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_no_ids_selected(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = []
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await namespace_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+namespaces+selected" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_invalid_ids(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["not-an-int"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        result = await namespace_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Invalid" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_no_namespaces_found(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        result = await namespace_bulk_delete(request=req, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "No+namespaces+found" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_bulk_delete_skips_default(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        default_ns = _make_namespace(id=1, slug="general")
        other_ns = _make_namespace(id=2, slug="custom")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [default_ns, other_ns]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_bulk_delete(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "1+namespace(s)+deleted" in result.headers.get("location", "")
        assert "1+skipped" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(other_ns)

    @pytest.mark.asyncio
    async def test_bulk_delete_comma_separated_selection(self):
        from internal.routes.namespaces import namespace_bulk_delete

        # The list page sends the whole selection as one comma-separated value
        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1,2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()

        ns1 = _make_namespace(id=1, slug="custom1")
        ns2 = _make_namespace(id=2, slug="custom2")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [ns1, ns2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_bulk_delete(request=req, db=db, auth_result=_make_user())

        assert "2+namespace(s)+deleted" in result.headers.get("location", "")
        assert db.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_no_default(self):
        from internal.routes.namespaces import namespace_bulk_delete

        req = _make_request()
        form_mock = MagicMock()
        form_mock.getlist.return_value = ["1", "2"]
        req.form = AsyncMock(return_value=form_mock)
        db = _make_db()
        user = _make_user()

        ns1 = _make_namespace(id=1, slug="custom1")
        ns2 = _make_namespace(id=2, slug="custom2")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [ns1, ns2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_bulk_delete(request=req, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "2+namespace(s)+deleted+successfully" in result.headers.get("location", "")


# =========================================================================
# Namespace Delete
# =========================================================================


class TestNamespaceDelete:
    @pytest.mark.asyncio
    async def test_redirect_when_not_authenticated(self):
        from internal.routes.namespaces import namespace_delete

        req = _make_request()
        db = _make_db()
        redirect = RedirectResponse(url="/auth/login")
        result = await namespace_delete(request=req, namespace_id=1, db=db, auth_result=redirect)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_not_found(self):
        from internal.routes.namespaces import namespace_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        result = await namespace_delete(request=req, namespace_id=999, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "error" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_prevent_delete_default(self):
        from internal.routes.namespaces import namespace_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(slug="general")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        result = await namespace_delete(request=req, namespace_id=1, db=db, auth_result=user)
        assert isinstance(result, RedirectResponse)
        assert "Cannot+delete" in result.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_delete_success(self):
        from internal.routes.namespaces import namespace_delete

        req = _make_request()
        db = _make_db()
        user = _make_user()

        ns = _make_namespace(slug="custom")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ns
        db.execute = AsyncMock(return_value=result_mock)

        with patch("internal.routes.namespaces.settings") as mock_settings:
            mock_settings.oauth2_client_id = "test-client"
            result = await namespace_delete(request=req, namespace_id=1, db=db, auth_result=user)

        assert isinstance(result, RedirectResponse)
        assert "success" in result.headers.get("location", "")
        db.delete.assert_awaited_once_with(ns)
        db.commit.assert_awaited_once()


# =========================================================================
# Constants
# =========================================================================


class TestConstants:
    def test_default_namespace_slug(self):
        from internal.routes.namespaces import DEFAULT_NAMESPACE_SLUG

        assert DEFAULT_NAMESPACE_SLUG == "general"
