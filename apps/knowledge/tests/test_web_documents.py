# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web documents routes (knowledge/routes/web/documents.py)."""

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
    return coll


def _make_mock_document(**overrides):
    doc = MagicMock()
    doc.id = overrides.get("id", uuid4())
    doc.collection_id = overrides.get("collection_id", uuid4())
    doc.content = overrides.get("content", "Test content")
    doc.content_size = overrides.get("content_size", len(b"Test content"))
    doc.content_hash = overrides.get("content_hash", "abc123")
    doc.embedding = overrides.get("embedding", [0.1] * 10)
    doc.source_type = overrides.get("source_type")
    doc.source_ref = overrides.get("source_ref")
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
def auth_context_with_tenant():
    return WebAuthContext(
        user=_make_user(),
        tenant=_make_mock_tenant(),
        tenant_member=_make_mock_member(),
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
# view_document
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.documents.templates")
async def test_view_document_success(mock_templates, web_client, mock_db):
    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id)
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),  # get document
            _make_result(scalar_one_or_none=coll),  # get collection
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "documents/detail.html"


async def test_view_document_no_tenant(web_client_no_tenant, mock_db):
    doc_id = uuid4()
    response = await web_client_no_tenant.get(f"/documents/{doc_id}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


async def test_view_document_not_found(web_client, mock_db):
    doc_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.get(f"/documents/{doc_id}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


# ---------------------------------------------------------------------------
# new_document_form
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.documents.templates")
async def test_new_document_form_success(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),  # verify collection
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/documents/{coll_id}/new")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "documents/form.html"
    ctx = call_args[0][2]
    assert ctx["is_edit"] is False
    assert ctx["document"] is None


@patch("knowledge.routes.web.documents.templates")
async def test_new_document_form_with_error(mock_templates, web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/documents/{coll_id}/new?error=Something+failed")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] == "Something failed"


async def test_new_document_form_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.get(f"/documents/{coll_id}/new", follow_redirects=False)
    assert response.status_code == 302


async def test_new_document_form_collection_not_found(web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.get(f"/documents/{coll_id}/new", follow_redirects=False)
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# create_document
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.documents.DocumentService")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_success(MockQuota, MockDocService, web_client, mock_db):
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=coll),
    )

    quota_instance = MockQuota.return_value
    quota_instance.enforce_document_quota = AsyncMock()
    quota_instance.enforce_storage_quota = AsyncMock()

    doc_instance = MockDocService.return_value
    doc_instance.create = AsyncMock()

    response = await web_client.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello world", "source_type": "manual", "source_ref": "ref1"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/collections/{coll_id}" in response.headers["location"]


async def test_create_document_no_tenant(web_client_no_tenant, mock_db):
    coll_id = uuid4()
    response = await web_client_no_tenant.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello"},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_create_document_collection_not_found(web_client, mock_db):
    coll_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"


@patch("knowledge.routes.web.documents.templates")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_quota_exceeded(MockQuota, mock_templates, web_client, mock_db):
    from knowledge.services.quotas import QuotaExceededError

    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=coll),  # verify collection
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )

    quota_instance = MockQuota.return_value
    quota_instance.enforce_document_quota = AsyncMock(
        side_effect=QuotaExceededError("max_total_documents", 100, 100)
    )

    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello", "source_type": "web", "source_ref": "http://x"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "Quota exceeded" in ctx["error"]
    assert ctx["form_content"] == "Hello"
    assert ctx["form_source_type"] == "web"
    assert ctx["form_source_ref"] == "http://x"


@patch("knowledge.routes.web.documents.DocumentService")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_create_document_service_error(MockQuota, MockDocService, web_client, mock_db):
    """When DocumentService.create raises, redirect with error."""
    coll_id = uuid4()
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=coll),
    )

    quota_instance = MockQuota.return_value
    quota_instance.enforce_document_quota = AsyncMock()
    quota_instance.enforce_storage_quota = AsyncMock()

    doc_instance = MockDocService.return_value
    doc_instance.create = AsyncMock(side_effect=RuntimeError("Embedding failed"))

    response = await web_client.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello", "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/new?error=" in response.headers["location"]
    mock_db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# edit_document_form
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.documents.templates")
async def test_edit_document_form_success(mock_templates, web_client, mock_db):
    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id)
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/documents/{doc_id}/edit")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["is_edit"] is True
    assert ctx["document"] is doc


@patch("knowledge.routes.web.documents.templates")
async def test_edit_document_form_with_error_param(mock_templates, web_client, mock_db):
    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id)
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/documents/{doc_id}/edit?error=previous+error")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] == "previous error"


async def test_edit_document_form_no_tenant(web_client_no_tenant, mock_db):
    doc_id = uuid4()
    response = await web_client_no_tenant.get(f"/documents/{doc_id}/edit", follow_redirects=False)
    assert response.status_code == 302


async def test_edit_document_form_not_found(web_client, mock_db):
    doc_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.get(f"/documents/{doc_id}/edit", follow_redirects=False)
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# update_document
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.documents.get_embedding_service")
async def test_update_document_content_changed(mock_embed_svc, web_client, mock_db):
    """Update document with changed content regenerates embedding."""
    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(
        id=doc_id, collection_id=coll_id, content="Old content", content_size=11
    )
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
        ]
    )

    embed_service = MagicMock()
    embed_service.embed_text = AsyncMock(return_value=[0.1] * 10)
    mock_embed_svc.return_value = embed_service

    response = await web_client.post(
        f"/documents/{doc_id}/edit",
        data={"content": "New content", "source_type": "manual", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/documents/{doc_id}" in response.headers["location"]
    embed_service.embed_text.assert_called_once_with("New content")


async def test_update_document_content_unchanged(web_client, mock_db):
    """Update document without content change skips embedding."""
    doc_id = uuid4()
    coll_id = uuid4()
    same_content = "Same content"
    doc = _make_mock_document(
        id=doc_id,
        collection_id=coll_id,
        content=same_content,
        content_size=len(same_content.encode("utf-8")),
    )
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
        ]
    )

    response = await web_client.post(
        f"/documents/{doc_id}/edit",
        data={"content": same_content, "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/documents/{doc_id}" in response.headers["location"]


async def test_update_document_no_tenant(web_client_no_tenant, mock_db):
    doc_id = uuid4()
    response = await web_client_no_tenant.post(
        f"/documents/{doc_id}/edit",
        data={"content": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_update_document_not_found(web_client, mock_db):
    doc_id = uuid4()
    mock_db.execute = AsyncMock(return_value=_make_result(scalar_one_or_none=None))

    response = await web_client.post(
        f"/documents/{doc_id}/edit",
        data={"content": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@patch("knowledge.routes.web.documents.templates")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_update_document_storage_quota_exceeded(
    MockQuota, mock_templates, web_client, mock_db
):
    """When content grows and storage quota is exceeded, show error."""
    from knowledge.services.quotas import QuotaExceededError

    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id, content="x", content_size=1)
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
            _make_result(scalars_all=[_make_mock_tenant()]),  # tenants for switcher
        ]
    )

    quota_instance = MockQuota.return_value
    quota_instance.enforce_storage_quota = AsyncMock(
        side_effect=QuotaExceededError("max_storage_bytes", 100, 100)
    )

    mock_templates.TemplateResponse.return_value = _html_response()

    # new content is larger
    response = await web_client.post(
        f"/documents/{doc_id}/edit",
        data={"content": "A" * 1000, "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert "Quota exceeded" in ctx["error"]


@patch("knowledge.routes.web.documents.get_embedding_service")
@patch("knowledge.routes.web.documents.QuotaService")
async def test_update_document_embedding_error(MockQuota, mock_embed_svc, web_client, mock_db):
    """When embedding regeneration fails, redirect with error."""
    quota_instance = MockQuota.return_value
    quota_instance.enforce_storage_quota = AsyncMock()

    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id, content="Old", content_size=3)
    coll = _make_mock_collection(id=coll_id)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalar_one_or_none=doc),
            _make_result(scalar_one_or_none=coll),
        ]
    )

    embed_service = MagicMock()
    embed_service.embed_text = AsyncMock(side_effect=RuntimeError("API down"))
    mock_embed_svc.return_value = embed_service

    response = await web_client.post(
        f"/documents/{doc_id}/edit",
        data={"content": "New content", "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/edit?error=" in response.headers["location"]
    mock_db.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------


async def test_delete_document_success(web_client, mock_db):
    doc_id = uuid4()
    coll_id = uuid4()
    doc = _make_mock_document(id=doc_id, collection_id=coll_id)

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=doc),
    )

    response = await web_client.post(
        f"/documents/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/collections/{coll_id}" in response.headers["location"]
    mock_db.delete.assert_called_once_with(doc)


async def test_delete_document_not_found(web_client, mock_db):
    doc_id = uuid4()
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalar_one_or_none=None),
    )

    response = await web_client.post(
        f"/documents/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/collections"
    mock_db.delete.assert_not_called()


async def test_delete_document_no_tenant(web_client_no_tenant, mock_db):
    doc_id = uuid4()
    response = await web_client_no_tenant.post(
        f"/documents/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Auth redirect tests — cover `isinstance(auth_result, RedirectResponse)`
# branches (lines 64, 109, 152, 233, 282, 371)
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


async def test_view_document_auth_redirect(web_client_redirect):
    """view_document returns redirect when auth is RedirectResponse (line 64)."""
    doc_id = uuid4()
    response = await web_client_redirect.get(f"/documents/{doc_id}", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_new_document_form_auth_redirect(web_client_redirect):
    """new_document_form returns redirect when auth is RedirectResponse (line 109)."""
    coll_id = uuid4()
    response = await web_client_redirect.get(f"/documents/{coll_id}/new", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_create_document_auth_redirect(web_client_redirect):
    """create_document returns redirect when auth is RedirectResponse (line 152)."""
    coll_id = uuid4()
    response = await web_client_redirect.post(
        f"/documents/{coll_id}/new",
        data={"content": "Hello", "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_edit_document_form_auth_redirect(web_client_redirect):
    """edit_document_form returns redirect when auth is RedirectResponse (line 233)."""
    doc_id = uuid4()
    response = await web_client_redirect.get(f"/documents/{doc_id}/edit", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_update_document_auth_redirect(web_client_redirect):
    """update_document returns redirect when auth is RedirectResponse (line 282)."""
    doc_id = uuid4()
    response = await web_client_redirect.post(
        f"/documents/{doc_id}/edit",
        data={"content": "x", "source_type": "", "source_ref": ""},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_delete_document_auth_redirect(web_client_redirect):
    """delete_document returns redirect when auth is RedirectResponse (line 371)."""
    doc_id = uuid4()
    response = await web_client_redirect.post(
        f"/documents/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]
