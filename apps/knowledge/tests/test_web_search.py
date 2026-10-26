# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web search routes (knowledge/routes/web/search.py)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import HTMLResponse

from knowledge.auth.dependencies import get_web_auth_context
from knowledge.auth.models import User, WebAuthContext
from knowledge.database import get_db
from knowledge.internal import internal_app
from knowledge.models.enums import PlanType
from knowledge.schemas.search import SearchResponse, SearchResult
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


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


def _make_search_response(results=None, query="test"):
    """Create a SearchResponse with optional results."""
    return SearchResponse(
        results=results or [],
        query=query,
        total_results=len(results) if results else 0,
    )


def _make_search_result(**overrides):
    """Create a SearchResult."""
    return SearchResult(
        document_id=overrides.get("document_id", uuid4()),
        collection_id=overrides.get("collection_id", uuid4()),
        collection_slug=overrides.get("collection_slug", "test-collection"),
        content=overrides.get("content", "Some matching content"),
        score=overrides.get("score", 0.95),
        metadata=overrides.get("metadata", {}),
    )


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
# GET /search - search_page
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.search.templates")
async def test_search_page_no_query(mock_templates, web_client, mock_db):
    """GET /search without a query returns the page with empty results."""
    coll = _make_mock_collection()
    mock_db.execute = AsyncMock(
        side_effect=[
            # 1st: collections for filter dropdown
            _make_result(scalars_all=[coll]),
            # 2nd: _get_common_context tenants for switcher
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search")
    assert response.status_code == 200
    mock_templates.TemplateResponse.assert_called_once()
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "pages/search.html"
    ctx = call_args[0][2]
    assert ctx["query"] == ""
    assert ctx["results"] == []
    assert ctx["collections"] == [coll]
    assert ctx["selected_collection"] == ""
    assert ctx["selected_collection_ids"] == ""
    assert ctx["selected_top_k"] == 20
    assert ctx["selected_threshold"] == 0.5
    assert ctx["selected_include_content"] is True
    assert ctx["selected_filters_json"] == ""
    assert "error" in ctx
    assert ctx["error"] is None


@patch("knowledge.routes.web.search.templates")
async def test_search_page_no_tenant(mock_templates, web_client_no_tenant, mock_db):
    """GET /search without tenant returns page with info message."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client_no_tenant.get("/search")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "pages/search.html"
    ctx = call_args[0][2]
    assert ctx["info"] == "No tenant selected"
    assert ctx["collections"] == []
    assert ctx["results"] == []
    assert ctx["query"] == ""


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_with_query(mock_templates, MockSearchService, web_client, mock_db):
    """GET /search?q=test performs a search and returns results."""
    coll = _make_mock_collection()
    search_result = _make_search_result()
    search_response = _make_search_response(results=[search_result], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            # 1st: collections for filter dropdown
            _make_result(scalars_all=[coll]),
            # 2nd: _get_common_context tenants for switcher
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    ctx = call_args[0][2]
    assert ctx["query"] == "test"
    assert ctx["results"] == [search_result]
    assert ctx["error"] is None
    # Verify SearchService was called
    MockSearchService.assert_called_once_with(mock_db)
    mock_search_instance.search.assert_called_once()


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_with_collection_filter(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test&collection_id=xxx passes collection_ids to SearchService."""
    coll_id = str(uuid4())
    search_response = _make_search_response(results=[], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get(f"/search?q=test&collection_id={coll_id}")
    assert response.status_code == 200

    # Verify the SearchRequest was built with collection_ids
    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.collection_ids == [coll_id]
    assert search_request.query == "test"

    # Verify template context
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["selected_collection"] == coll_id


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_with_l2_distance_type(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test&distance_type=l2 uses the l2 distance metric."""
    search_response = _make_search_response(results=[], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test&distance_type=l2")
    assert response.status_code == 200

    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.distance_type == "l2"

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["selected_distance_type"] == "l2"


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_with_inner_product_distance(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test&distance_type=inner_product uses inner_product metric."""
    search_response = _make_search_response(results=[], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test&distance_type=inner_product")
    assert response.status_code == 200

    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.distance_type == "inner_product"

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["selected_distance_type"] == "inner_product"


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_invalid_distance_type_defaults_to_cosine(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test&distance_type=bogus falls back to cosine."""
    search_response = _make_search_response(results=[], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test&distance_type=bogus")
    assert response.status_code == 200

    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.distance_type == "cosine"

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["selected_distance_type"] == "cosine"


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_search_service_error(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test with SearchService raising returns error in context."""
    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(side_effect=RuntimeError("embedding service down"))

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test")
    assert response.status_code == 200

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["results"] == []
    assert ctx["error"] is not None
    assert "Search failed" in ctx["error"]
    assert "embedding service down" in ctx["error"]


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_no_collection_filter(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search?q=test without collection_id passes None for collection_ids."""
    search_response = _make_search_response(results=[], query="test")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test")
    assert response.status_code == 200

    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.collection_ids is None


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_search_request_params(
    mock_templates, MockSearchService, web_client, mock_db
):
    """Verify SearchRequest is built with correct default params."""
    search_response = _make_search_response(results=[], query="hello world")

    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=hello+world")
    assert response.status_code == 200

    search_call_args = mock_search_instance.search.call_args
    search_request = search_call_args[0][1]
    assert search_request.query == "hello world"
    assert search_request.top_k == 20
    assert search_request.threshold == 0.5
    assert search_request.distance_type == "cosine"
    assert search_request.filters is None
    assert search_request.include_content is True


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_with_all_search_request_fields(
    mock_templates, MockSearchService, web_client, mock_db
):
    """GET /search passes all SearchRequest fields when provided."""
    search_response = _make_search_response(results=[], query="hello")
    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(return_value=search_response)

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    url = (
        "/search?q=hello"
        "&collection_id=cid1"
        "&collection_ids=slug-a,slug-b"
        "&top_k=7"
        "&threshold=0.23"
        "&distance_type=l2"
        "&include_content=false"
        "&filters_json=%7B%22source_type%22%3A%22manual%22%7D"
    )
    response = await web_client.get(url)
    assert response.status_code == 200

    search_request = mock_search_instance.search.call_args[0][1]
    assert search_request.query == "hello"
    assert search_request.collection_ids == ["slug-a", "slug-b", "cid1"]
    assert search_request.top_k == 7
    assert search_request.threshold == 0.23
    assert search_request.distance_type == "l2"
    assert search_request.include_content is False
    assert search_request.filters == {"source_type": "manual"}


# ---------------------------------------------------------------------------
# POST /search - search_submit
# ---------------------------------------------------------------------------


async def test_search_submit_redirects_with_query(web_client):
    """POST /search with query redirects to GET /search?q=..."""
    response = await web_client.post(
        "/search",
        data={"query": "my search", "collection_id": "", "distance_type": "cosine"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "/search?q=my" in location
    assert "search" in location
    # Default distance_type cosine should NOT appear in URL
    assert "distance_type" not in location


async def test_search_submit_redirects_with_collection_id(web_client):
    """POST /search with collection_id includes it in the redirect."""
    coll_id = str(uuid4())
    response = await web_client.post(
        "/search",
        data={"query": "test", "collection_id": coll_id, "distance_type": "cosine"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert f"collection_ids={coll_id}" in location


async def test_search_submit_redirects_with_distance_type(web_client):
    """POST /search with non-default distance_type includes it in the redirect."""
    response = await web_client.post(
        "/search",
        data={"query": "test", "collection_id": "", "distance_type": "l2"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "distance_type=l2" in location


async def test_search_submit_empty_query_redirects(web_client):
    """POST /search with empty query still redirects."""
    response = await web_client.post(
        "/search",
        data={"query": "", "collection_id": "", "distance_type": "cosine"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "/search?q=" in location


async def test_search_submit_no_tenant_redirects(web_client_no_tenant):
    """POST /search without tenant returns a redirect (from auth)."""
    response = await web_client_no_tenant.post(
        "/search",
        data={"query": "test", "collection_id": "", "distance_type": "cosine"},
        follow_redirects=False,
    )
    # With no tenant, auth_result is still WebAuthContext (not RedirectResponse),
    # so the route proceeds to build the redirect URL
    assert response.status_code == 302
    location = response.headers["location"]
    assert "/search?q=test" in location


async def test_search_submit_all_params(web_client):
    """POST /search with all params includes them in redirect URL."""
    coll_id = str(uuid4())
    response = await web_client.post(
        "/search",
        data={
            "query": "semantic search",
            "collection_id": coll_id,
            "distance_type": "inner_product",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "q=semantic" in location
    assert f"collection_ids={coll_id}" in location
    assert "distance_type=inner_product" in location


async def test_search_submit_redirects_with_advanced_fields(web_client):
    """POST /search includes advanced SearchRequest fields in redirect URL."""
    response = await web_client.post(
        "/search",
        data={
            "query": "semantic search",
            "collection_id": "",
            "collection_ids": "slug1,slug2",
            "top_k": "12",
            "threshold": "0.22",
            "distance_type": "l2",
            "include_content": "false",
            "filters_json": '{"source_type":"manual"}',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    assert "collection_ids=slug1%2Cslug2" in location
    assert "top_k=12" in location
    assert "threshold=0.22" in location
    assert "distance_type=l2" in location
    assert "include_content=false" in location
    assert "filters_json=%7B%22source_type%22%3A%22manual%22%7D" in location


# ---------------------------------------------------------------------------
# GET /search - _get_common_context
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.search.templates")
async def test_common_context_includes_active_section(mock_templates, web_client, mock_db):
    """Verify _get_common_context sets active_section to 'search'."""
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search")
    assert response.status_code == 200

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["active_section"] == "search"


@patch("knowledge.routes.web.search.templates")
async def test_common_context_includes_user_and_tenant(
    mock_templates, web_client, mock_db, auth_context_with_tenant
):
    """Verify _get_common_context passes user and tenant into template."""
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search")
    assert response.status_code == 200

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["user"].id == TEST_USER_ID
    assert ctx["tenant"] is not None
    assert ctx["tenant"].id == TEST_TENANT_ID


@patch("knowledge.routes.web.search.templates")
async def test_common_context_tenants_for_switcher(mock_templates, web_client, mock_db):
    """Verify _get_common_context fetches tenants for the switcher."""
    tenant1 = _make_mock_tenant(name="Org A")
    tenant2 = _make_mock_tenant(id=uuid4(), name="Org B")
    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # collections
            _make_result(scalars_all=[tenant1, tenant2]),  # tenants for switcher
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search")
    assert response.status_code == 200

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert len(ctx["tenants"]) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.fixture
async def web_client_redirect(mock_db):
    """Client where auth returns a RedirectResponse."""
    from starlette.responses import RedirectResponse as StRedirect

    internal_app.dependency_overrides[get_db] = lambda: mock_db
    internal_app.dependency_overrides[get_web_auth_context] = lambda: StRedirect(
        url="/auth/login", status_code=302
    )

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


async def test_search_page_auth_redirect(web_client_redirect):
    """GET /search with auth redirect returns 302 to login (line 62)."""
    response = await web_client_redirect.get("/search", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


async def test_search_submit_auth_redirect(web_client_redirect):
    """POST /search with auth redirect returns 302 to login (line 146)."""
    response = await web_client_redirect.post(
        "/search",
        data={"query": "test", "collection_id": "", "distance_type": "cosine"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/auth/login" in response.headers["location"]


@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_error_message_truncated(
    mock_templates, MockSearchService, web_client, mock_db
):
    """Verify error messages are truncated to 200 chars."""
    long_message = "x" * 500
    mock_search_instance = MockSearchService.return_value
    mock_search_instance.search = AsyncMock(side_effect=RuntimeError(long_message))

    mock_db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),
            _make_result(scalars_all=[_make_mock_tenant()]),
        ]
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/search?q=test")
    assert response.status_code == 200

    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] is not None
    # "Search failed: " prefix + 200 chars of the error
    assert len(ctx["error"]) <= len("Search failed: ") + 200
