# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the role edit page of the administration console (roles_pages.py)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote

import pytest
from auth.api.routes.admin import roles_pages
from auth.api.routes.admin.roles_pages import (
    require_roles_write,
    role_edit_page,
    role_edit_submit,
)
from auth.services.role import RoleService
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

MODULE = "auth.api.routes.admin.roles_pages"


def _auth():
    return (MagicMock(), [MagicMock()])


def _scope(name, *, active=True, description=None):
    scope = MagicMock()
    scope.id = uuid.uuid4()
    scope.name = name
    scope.description = description or f"About {name}"
    scope.is_active = active
    return scope


def _role(*, is_system=False, scopes=("users:read",), name="editor"):
    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = name
    role.description = "Can edit"
    role.is_system = is_system
    role.created_at = None
    role.updated_at = None
    role.role_scopes = [MagicMock(scope=_scope(s), scope_id=uuid.uuid4()) for s in scopes]
    role.get_all_scope_names.return_value = list(scopes)
    return role


def _request(**query):
    request = MagicMock()
    request.query_params = query
    return request


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def test_the_edit_routes_require_roles_write():
    routes = [r for r in roles_pages.router.routes if r.path == "/roles/{role_id}/edit"]
    assert {m for r in routes for m in r.methods} == {"GET", "POST"}
    for route in routes:
        assert require_roles_write in [d.call for d in route.dependant.dependencies]


class TestEditPage:
    async def test_form_lists_the_scopes_and_checks_the_held_ones(self):
        role = _role(scopes=("users:read", "notes:read"))
        templates = MagicMock()
        service, scopes = AsyncMock(), AsyncMock()
        service.get_by_id.return_value = role
        scopes.list_active.return_value = [_scope("notes:read"), _scope("notes:write")]
        with (
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(f"{MODULE}._role_service", service),
            patch(f"{MODULE}._scope_service", scopes),
        ):
            await role_edit_page(
                request=_request(), role_id=str(role.id), db=AsyncMock(), auth=_auth()
            )

        context = templates.TemplateResponse.call_args.kwargs["context"]
        assert templates.TemplateResponse.call_args.kwargs["name"] == "admin/roles/edit.html"
        assert context["role"]["id"] == str(role.id)
        # built-in scopes first, then the other active scopes
        names = list(context["available_scopes"])
        assert names.index("users:read") < names.index("notes:write")
        assert "notes:write" in names
        assert context["held_scopes"] == ["users:read", "notes:read"]

    async def test_a_held_scope_that_is_listed_nowhere_is_still_offered(self):
        role = _role(scopes=("legacy:thing",))
        templates = MagicMock()
        service, scopes = AsyncMock(), AsyncMock()
        service.get_by_id.return_value = role
        scopes.list_active.return_value = []
        with (
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(f"{MODULE}._role_service", service),
            patch(f"{MODULE}._scope_service", scopes),
        ):
            await role_edit_page(
                request=_request(), role_id=str(role.id), db=AsyncMock(), auth=_auth()
            )
        context = templates.TemplateResponse.call_args.kwargs["context"]
        assert "legacy:thing" in context["available_scopes"]

    async def test_error_message_is_passed_to_the_template(self):
        role = _role()
        templates = MagicMock()
        service, scopes = AsyncMock(), AsyncMock()
        service.get_by_id.return_value = role
        scopes.list_active.return_value = []
        with (
            patch(f"{MODULE}.get_templates", return_value=templates),
            patch(f"{MODULE}._role_service", service),
            patch(f"{MODULE}._scope_service", scopes),
        ):
            await role_edit_page(
                request=_request(error="Invalid scopes: x"),
                role_id=str(role.id),
                db=AsyncMock(),
                auth=_auth(),
            )
        assert templates.TemplateResponse.call_args.kwargs["context"]["error"] == (
            "Invalid scopes: x"
        )

    async def test_system_role_is_refused_with_a_message(self):
        role = _role(is_system=True)
        service = AsyncMock()
        service.get_by_id.return_value = role
        with patch(f"{MODULE}._role_service", service), patch(f"{MODULE}.get_templates"):
            result = await role_edit_page(
                request=_request(), role_id=str(role.id), db=AsyncMock(), auth=_auth()
            )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert result.headers["location"] == (
            f"/admin/roles/{role.id}?error=System+roles+cannot+be+modified"
        )

    async def test_invalid_id_is_a_bad_request(self):
        with patch(f"{MODULE}.get_templates"), pytest.raises(HTTPException) as caught:
            await role_edit_page(request=_request(), role_id="nope", db=AsyncMock(), auth=_auth())
        assert caught.value.status_code == 400

    async def test_unknown_role_is_not_found(self):
        service = AsyncMock()
        service.get_by_id.return_value = None
        with (
            patch(f"{MODULE}._role_service", service),
            patch(f"{MODULE}.get_templates"),
            pytest.raises(HTTPException) as caught,
        ):
            await role_edit_page(
                request=_request(), role_id=str(uuid.uuid4()), db=AsyncMock(), auth=_auth()
            )
        assert caught.value.status_code == 404


class TestEditSubmit:
    async def test_saves_the_description_and_merges_the_scope_inputs(self):
        role = _role()
        service = AsyncMock()
        service.get_by_id.return_value = role
        with patch(f"{MODULE}._role_service", service):
            result = await role_edit_submit(
                role_id=str(role.id),
                db=AsyncMock(),
                auth=_auth(),
                description="Can edit",
                scopes=["users:read", "users:write"],
                wildcard_scopes="users:write, sessions:*,",
            )
        service.update_role_by_scope_names.assert_awaited_once()
        kwargs = service.update_role_by_scope_names.call_args.kwargs
        assert kwargs["description"] == "Can edit"
        assert kwargs["scope_names"] == ["users:read", "users:write", "sessions:*"]
        assert result.status_code == 303
        assert result.headers["location"] == (
            f"/admin/roles/{role.id}?success=Role+updated+successfully"
        )

    async def test_an_empty_description_is_stored_as_none(self):
        role = _role()
        service = AsyncMock()
        service.get_by_id.return_value = role
        with patch(f"{MODULE}._role_service", service):
            await role_edit_submit(
                role_id=str(role.id), db=AsyncMock(), auth=_auth(), description=""
            )
        assert service.update_role_by_scope_names.call_args.kwargs["description"] is None

    async def test_invalid_scopes_come_back_to_the_form(self):
        role = _role()
        service = AsyncMock()
        service.get_by_id.return_value = role
        service.update_role_by_scope_names.side_effect = ValueError("Invalid scopes: nope")
        with patch(f"{MODULE}._role_service", service):
            result = await role_edit_submit(
                role_id=str(role.id), db=AsyncMock(), auth=_auth(), scopes=["nope"]
            )
        assert unquote(result.headers["location"]) == (
            f"/admin/roles/{role.id}/edit?error=Invalid scopes: nope"
        )

    async def test_system_role_is_refused(self):
        role = _role(is_system=True)
        service = AsyncMock()
        service.get_by_id.return_value = role
        service.update_role_by_scope_names.side_effect = ValueError(
            "System roles cannot be modified"
        )
        with patch(f"{MODULE}._role_service", service):
            result = await role_edit_submit(role_id=str(role.id), db=AsyncMock(), auth=_auth())
        assert result.headers["location"] == (
            f"/admin/roles/{role.id}?error=System+roles+cannot+be+modified"
        )

    async def test_invalid_id_and_unknown_role_go_back_to_the_list(self):
        service = AsyncMock()
        service.get_by_id.return_value = None
        with patch(f"{MODULE}._role_service", service):
            bad = await role_edit_submit(role_id="nope", db=AsyncMock(), auth=_auth())
            missing = await role_edit_submit(
                role_id=str(uuid.uuid4()), db=AsyncMock(), auth=_auth()
            )
        assert bad.headers["location"] == "/admin/roles?error=Invalid+role+ID+format"
        assert missing.headers["location"] == "/admin/roles?error=Role+not+found"
        service.update_role_by_scope_names.assert_not_awaited()


def test_unique_scopes_keeps_the_order():
    assert roles_pages._unique_scopes(["b", "a"], "a, c") == ["b", "a", "c"]
    assert roles_pages._unique_scopes(None, None) == []


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


def _link(scope):
    return MagicMock(scope=scope, scope_id=scope.id)


class TestUpdateRoleByScopeNames:
    @pytest.fixture
    def repo(self):
        repo = AsyncMock()
        repo.find_scopes_by_names.side_effect = lambda db, names: {
            n: _scope(n) for n in names if n != "unknown"
        }
        return repo

    async def test_replaces_the_scopes_and_keeps_the_ones_that_stay(self, repo):
        kept, dropped = _scope("users:read"), _scope("users:write")
        repo.find_scopes_by_names.side_effect = None
        repo.find_scopes_by_names.return_value = {
            "users:read": kept,
            "sessions:read": _scope("sessions:read"),
        }
        role = _role(scopes=())
        role.role_scopes = [_link(kept), _link(dropped)]
        db = AsyncMock()
        added = []
        repo.add.side_effect = lambda _db, row: added.append(row)

        await RoleService(repository=repo).update_role_by_scope_names(
            db, role, description="New", scope_names=["users:read", "sessions:read"]
        )

        assert role.description == "New"
        repo.delete.assert_awaited_once_with(db, role.role_scopes[1])
        assert [row.scope_id for row in added] == [
            repo.find_scopes_by_names.return_value["sessions:read"].id
        ]
        db.commit.assert_awaited_once()

    async def test_keeps_the_assignments_of_disabled_scopes(self, repo):
        disabled = _scope("old:thing", active=False)
        role = _role(scopes=())
        role.role_scopes = [_link(disabled)]
        await RoleService(repository=repo).update_role_by_scope_names(
            AsyncMock(), role, description=None, scope_names=[]
        )
        repo.delete.assert_not_awaited()

    async def test_unknown_scope_changes_nothing(self, repo):
        role = _role()
        db = AsyncMock()
        with pytest.raises(ValueError, match="Invalid scopes: unknown"):
            await RoleService(repository=repo).update_role_by_scope_names(
                db, role, description="x", scope_names=["users:read", "unknown"]
            )
        db.commit.assert_not_awaited()
        repo.delete.assert_not_awaited()

    async def test_system_role_is_refused(self, repo):
        role = _role(is_system=True)
        with pytest.raises(ValueError, match="System roles cannot be modified"):
            await RoleService(repository=repo).update_role_by_scope_names(
                AsyncMock(), role, description="x", scope_names=[]
            )
        repo.find_scopes_by_names.assert_not_awaited()
