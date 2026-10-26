# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web collections routes (knowledge/routes/web/collections.py)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.responses import RedirectResponse
from httpx import ASGITransport, AsyncClient
from starlette.responses import HTMLResponse

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.internal import internal_app
from knowledge.models.enums import PlanType
from tests.conftest import TEST_TENANT_ID, TEST_USER_ID


def _html_response(status_code=200):
    """Return a real HTMLResponse for template mock return values."""
    return HTMLResponse(content="<html>ok</html>", status_code=status_code)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_tenant(**overrides):
    tenant = MagicMock()
    tenant.id = overrides.get("id", TEST_TENANT_ID)
    tenant.name = overrides.get("name", "Test Org")
    tenant.slug = overrides.get("slug", "test-org")
    tenant.plan = overrides.get("plan", PlanType.FREE)
    tenant.is_active = True
    return tenant


def _make_mock_member(**overrides):
    member = MagicMock()
    member.id = overrides.get("id", uuid4())
    member.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    member.user_id = overrides.get("user_id", TEST_USER_ID)
    member.is_owner = overrides.get("is_owner", True)
    member.is_admin = overrides.get("is_admin", True)
    member.can_manage_members = overrides.get("can_manage_members", True)
    member.can_manage_tenant = overrides.get("can_manage_tenant", True)
    return member


def _make_user():
    return User(
        id=TEST_USER_ID,
        email="test@example.com",
        name="Test User",
        scopes=["collections:read", "collections:write", "documents:read", "documents:write"],
    )


def _make_mock_collection(**overrides):
    coll = MagicMock()
    coll.id = overrides.get("id", uuid4())
    coll.organization_id = overrides.get("organization_id", TEST_TENANT_ID)
    coll.name = overrides.get("name", "Test Collection")
    coll.slug = overrides.get("slug", "test-collection")
    coll.description = overrides.get("description", "A test collection")
    coll.created_at = overrides.get("created_at", datetime.now(UTC))
    coll.updated_at = overrides.get("updated_at", datetime.now(UTC))
    return coll


def _make_mock_document(**overrides):
    doc = MagicMock()
    doc.id = overrides.get("id", uuid4())
    doc.collection_id = overrides.get("collection_id", uuid4())
    doc.content = overrides.get("content", "Test content")
    doc.content_size = overrides.get("content_size", len(doc.content.encode("utf-8")))
    doc.created_at = overrides.get("created_at", datetime.now(UTC))
    return doc


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_tenant():
    return _make_mock_tenant()


@pytest.fixture
def mock_member():
    return _make_mock_member()


@pytest.fixture
def auth_context_with_tenant(mock_tenant, mock_member):
    return WebAuthContext(
        user=_make_user(),
        tenant=mock_tenant,
        tenant_member=mock_member,
    )


@pytest.fixture
def auth_context_no_tenant():
    return WebAuthContext(
        user=_make_user(),
        tenant=None,
        tenant_member=None,
    )


@pytest.fixture
async def web_client(mock_db, auth_context_with_tenant):
    """Create a test client for the internal app with mocked deps."""

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth_context_with_tenant

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


@pytest.fixture
async def web_client_no_tenant(mock_db, auth_context_no_tenant):
    """Client where auth has no tenant."""

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: auth_context_no_tenant

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Slugify tests
# ---------------------------------------------------------------------------


def test_slugify():
    from knowledge.routes.web.collections import slugify

    assert slugify("Hello World") == "hello-world"
    assert slugify("  Hello  World  ") == "hello-world"
    assert slugify("Test!@#$%") == "test"
    assert slugify("a" * 200) == "a" * 100
    assert slugify("---") == "collection"
    assert slugify("") == "collection"


# ---------------------------------------------------------------------------
# list_collections
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
async def test_list_collections_success(mock_templates, web_client, mock_db):
    """List collections with tenant."""
    coll = _make_mock_collection()
    # 1st call: _get_common_context tenants
    # 2nd call: count
    # 3rd call: collections list
    # 4th call: doc count per collection
    # 5th call: template render in _get_common_context
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
            _make_result(scalar=1),  # total count
            _make_result(scalars_all=[coll]),  # collections
            _make_result(scalar=5),  # doc count for coll
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants (2nd call in template)
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/collections")
    assert response.status_code == 200
    mock_templates.TemplateResponse.assert_called_once()
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "collections/list.html"


@patch("knowledge.routes.web.collections.templates")
async def test_list_collections_no_tenant(mock_templates, web_client_no_tenant, mock_db):
    """List collections without tenant shows error."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_tenant.get("/collections")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "collections/list.html"
    ctx = call_args[0][2]
    assert ctx["error"] == "No tenant selected"


# ---------------------------------------------------------------------------
# new_collection_form
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
async def test_new_collection_form(mock_templates, web_client, mock_db):
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[_make_mock_tenant()]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/collections/new")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "collections/form.html"
    ctx = call_args[0][2]
    assert ctx["is_edit"] is False
    assert ctx["collection"] is None


# ---------------------------------------------------------------------------
# create_collection
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
@patch("knowledge.routes.web.collections.QuotaService")
async def test_create_collection_success(MockQuotaService, mock_templates, web_client, mock_db):
    """Create collection successfully redirects."""
    quota_instance = MockQuotaService.return_value
    quota_instance.enforce_collection_quota = AsyncMock()

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[_make_mock_tenant()]),
    )

    response = await web_client.post(
        "/collections/new",
        data={"name": "My Collection", "description": "Desc"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/collections/" in response.headers["location"]


@patch("knowledge.routes.web.collections.templates")
@patch("knowledge.routes.web.collections.QuotaService")
async def test_create_collection_no_tenant(
    MockQuotaService, mock_templates, web_client_no_tenant, mock_db
):
    """Create collection without tenant shows error."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_tenant.post(
        "/collections/new",
        data={"name": "My Collection", "description": "Desc"},
    )
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    ctx = call_args[0][2]
    assert ctx["error"] == "No tenant selected"


@patch("knowledge.routes.web.collections.templates")
@patch("knowledge.routes.web.collections.QuotaService")
async def test_create_collection_quota_exceeded(
    MockQuotaService, mock_templates, web_client, mock_db
):
    """Create collection when quota exceeded shows error."""
    from knowledge.services.quotas import QuotaExceededError

    quota_instance = MockQuotaService.return_value
    quota_instance.enforce_collection_quota = AsyncMock(
        side_effect=QuotaExceededError("max_collections", 3, 3)
    )

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[_make_mock_tenant()]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post(
        "/collections/new",
        data={"name": "My Collection", "description": "Desc"},
    )
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    ctx = call_args[0][2]
    assert "Quota exceeded" in ctx["error"]
    assert ctx["form_name"] == "My Collection"
    assert ctx["form_description"] == "Desc"


@patch("knowledge.routes.web.collections.templates")
@patch("knowledge.routes.web.collections.QuotaService")
async def test_create_collection_name_already_used(
    MockQuotaService, mock_templates, web_client, mock_db
):
    """A second collection with the same slug is refused with an explanation, not a 500."""
    quota_instance = MockQuotaService.return_value
    quota_instance.enforce_collection_quota = AsyncMock()

    mock_db.execute = AsyncMock(
        return_value=_make_result(
            scalar_one_or_none=MagicMock(), scalars_all=[_make_mock_tenant()]
        ),
    )
    mock_templates.TemplateResponse.return_value = _html_response(status_code=400)

    response = await web_client.post(
        "/collections/new",
        data={"name": "My Collection", "description": "Desc"},
    )
    assert response.status_code == 400
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "already exists" in ctx["error"]
    assert ctx["form_name"] == "My Collection"
    mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# view_collection
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
async def test_view_collection_success(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    doc = _make_mock_document(collection_id=coll_id, content="hello world", content_size=0)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),  # get collection
            _make_result(scalar=3),  # doc count
            _make_result(scalars_all=[doc]),  # documents
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/collections/{coll_id}")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "collections/detail.html"
    ctx = call_args[0][2]
    assert ctx["display_document_sizes"][doc.id] == len(b"hello world")


async def test_view_collection_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.get(f"/collections/{coll_id}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


@patch("knowledge.routes.web.collections.templates")
async def test_view_collection_not_found(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.get(f"/collections/{coll_id}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


# ---------------------------------------------------------------------------
# edit_collection_form
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
async def test_edit_collection_form_success(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),  # get collection
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/collections/{coll_id}/edit")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "collections/form.html"
    ctx = call_args[0][2]
    assert ctx["is_edit"] is True


async def test_edit_collection_form_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.get(
        f"/collections/{coll_id}/edit", follow_redirects=False
    )
    assert response.status_code == 302


@patch("knowledge.routes.web.collections.templates")
async def test_edit_collection_form_not_found(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.get(f"/collections/{coll_id}/edit", follow_redirects=False)
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# update_collection
# ---------------------------------------------------------------------------


async def test_update_collection_success(web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=coll),
    )

    response = await web_client.post(
        f"/collections/{coll_id}/edit",
        data={"name": "Updated", "description": "New desc"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/collections/{coll.id}" in response.headers["location"]
    assert coll.name == "Updated"
    assert coll.description == "New desc"


async def test_update_collection_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.post(
        f"/collections/{coll_id}/edit",
        data={"name": "Updated", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_update_collection_not_found(web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/collections/{coll_id}/edit",
        data={"name": "Updated", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


async def test_update_collection_empty_description(web_client, mock_db):
    """Update collection with empty description sets it to None."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=coll),
    )

    response = await web_client.post(
        f"/collections/{coll_id}/edit",
        data={"name": "Updated", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert coll.description is None


# ---------------------------------------------------------------------------
# delete_collection
# ---------------------------------------------------------------------------


async def test_delete_collection_success(web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=coll),
    )

    response = await web_client.post(
        f"/collections/{coll_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"
    mock_db.delete.assert_called_once_with(coll)


async def test_delete_collection_not_found(web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=None),
    )

    response = await web_client.post(
        f"/collections/{coll_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"
    mock_db.delete.assert_not_called()


async def test_delete_collection_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.post(
        f"/collections/{coll_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# delete_selected_documents
# ---------------------------------------------------------------------------


async def test_delete_selected_documents_success(mock_db, auth_context_with_tenant):
    from knowledge.routes.web.collections import delete_selected_documents

    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    doc1 = _make_mock_document(id=uuid4(), collection_id=coll_id)
    doc2 = _make_mock_document(id=uuid4(), collection_id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),
            _make_result(scalars_all=[doc1, doc2]),
        ],
    )
    response = await delete_selected_documents(
        request=MagicMock(),
        collection_id=coll_id,
        document_ids=[doc1.id, doc2.id],
        db=mock_db,
        auth_result=auth_context_with_tenant,
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"/collections/{coll_id}"
    assert mock_db.delete.await_count == 2
    mock_db.commit.assert_awaited_once()


async def test_delete_selected_documents_empty_selection(mock_db, auth_context_with_tenant):
    from knowledge.routes.web.collections import delete_selected_documents

    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=coll))

    response = await delete_selected_documents(
        request=MagicMock(),
        collection_id=coll_id,
        document_ids=[],
        db=mock_db,
        auth_result=auth_context_with_tenant,
    )
    assert response.status_code == 302
    assert response.headers["location"] == f"/collections/{coll_id}"
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_awaited()


async def test_delete_selected_documents_collection_not_found(mock_db, auth_context_with_tenant):
    from knowledge.routes.web.collections import delete_selected_documents

    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await delete_selected_documents(
        request=MagicMock(),
        collection_id=coll_id,
        document_ids=[uuid4()],
        db=mock_db,
        auth_result=auth_context_with_tenant,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"
    mock_db.delete.assert_not_called()
    mock_db.commit.assert_not_awaited()


async def test_delete_selected_documents_no_tenant(mock_db, auth_context_no_tenant):
    from knowledge.routes.web.collections import delete_selected_documents

    coll_id = uuid4()
    response = await delete_selected_documents(
        request=MagicMock(),
        collection_id=coll_id,
        document_ids=[uuid4()],
        db=mock_db,
        auth_result=auth_context_no_tenant,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


# ---------------------------------------------------------------------------
# Auth redirect tests — cover `isinstance(auth_result, RedirectResponse)`
# branches (lines 74, 139, 161, 222, 282, 322, 361)
# ---------------------------------------------------------------------------


@pytest.fixture
async def web_client_redirect(mock_db):
    """Client where get_web_auth_context returns a RedirectResponse."""
    redirect = RedirectResponse(url="/auth/login", status_code=302)

    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: redirect

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


async def test_list_collections_auth_redirect(web_client_redirect):
    """list_collections returns redirect when auth is RedirectResponse (line 74)."""
    response = await web_client_redirect.get("/collections", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_new_collection_form_auth_redirect(web_client_redirect):
    """new_collection_form returns redirect when auth is RedirectResponse (line 139)."""
    response = await web_client_redirect.get("/collections/new", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_create_collection_auth_redirect(web_client_redirect):
    """create_collection returns redirect when auth is RedirectResponse (line 161)."""
    response = await web_client_redirect.post(
        "/collections/new",
        data={"name": "Test", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_view_collection_auth_redirect(web_client_redirect):
    """view_collection returns redirect when auth is RedirectResponse (line 222)."""
    coll_id = uuid4()
    response = await web_client_redirect.get(f"/collections/{coll_id}", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_edit_collection_form_auth_redirect(web_client_redirect):
    """edit_collection_form returns redirect when auth is RedirectResponse (line 282)."""
    coll_id = uuid4()
    response = await web_client_redirect.get(f"/collections/{coll_id}/edit", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_update_collection_auth_redirect(web_client_redirect):
    """update_collection returns redirect when auth is RedirectResponse (line 322)."""
    coll_id = uuid4()
    response = await web_client_redirect.post(
        f"/collections/{coll_id}/edit",
        data={"name": "Test", "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_delete_collection_auth_redirect(web_client_redirect):
    """delete_collection returns redirect when auth is RedirectResponse (line 361)."""
    coll_id = uuid4()
    response = await web_client_redirect.post(
        f"/collections/{coll_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_delete_selected_documents_auth_redirect():
    from knowledge.routes.web.collections import delete_selected_documents

    coll_id = uuid4()
    response = await delete_selected_documents(
        request=MagicMock(),
        collection_id=coll_id,
        document_ids=[uuid4()],
        db=AsyncMock(),
        auth_result=RedirectResponse(url="/auth/login", status_code=302),
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


# ---------------------------------------------------------------------------
# list_collections with collections that have documents (lines 113-116)
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.collections.templates")
async def test_list_collections_with_doc_counts(mock_templates, web_client, mock_db):
    """list_collections iterates over collections and counts docs (lines 113-116)."""
    coll1 = _make_mock_collection(id=uuid4(), name="Col A")
    coll2 = _make_mock_collection(id=uuid4(), name="Col B")

    # Execution order in list_collections:
    # 1. total count
    # 2. collections list
    # 3. doc count for coll1
    # 4. doc count for coll2
    # 5. _get_common_context -> tenants for switcher
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar=2),  # total count
            _make_result(scalars_all=[coll1, coll2]),  # collections
            _make_result(scalar=3),  # doc count for coll1
            _make_result(scalar=7),  # doc count for coll2
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/collections")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    ctx = call_args[0][2]
    assert len(ctx["collections"]) == 2
    # Verify doc counts were computed for both collections
    assert coll1.id in ctx["collection_stats"]
    assert coll2.id in ctx["collection_stats"]
