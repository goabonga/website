# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for web search route edge branches."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.responses import HTMLResponse

from knowledge.auth.models import User, WebAuthContext
from knowledge.models.enums import PlanType
from knowledge.routes.web.search import search_page, search_submit


def _make_result(scalars_all=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


def _make_auth_context():
    user = User(
        id=uuid4(),
        email="test@example.com",
        name="Test User",
        scopes=["collections:read"],
    )
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Org"
    tenant.plan = PlanType.FREE
    tenant.is_active = True
    member = MagicMock()
    member.is_admin = True
    member.is_owner = True
    member.organization_id = tenant.id
    return WebAuthContext(user=user, tenant=tenant, tenant_member=member)


@pytest.mark.asyncio
@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_clamps_invalid_top_k_and_threshold(mock_templates, mock_search_service):
    """Lines 97 and 99: invalid numeric controls should fallback to defaults."""
    mock_templates.TemplateResponse.return_value = HTMLResponse("ok", status_code=200)

    search_instance = mock_search_service.return_value
    search_instance.search = AsyncMock(
        return_value=MagicMock(results=[], query="q", total_results=0)
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # collections
            _make_result(scalars_all=[]),  # tenants in _get_common_context
        ]
    )

    response = await search_page(
        request=MagicMock(),
        q="q",
        collection_id="",
        collection_ids="",
        top_k=0,
        threshold=2.0,
        distance_type="cosine",
        include_content=True,
        filters_json="",
        db=db,
        auth_result=_make_auth_context(),
    )

    assert response.status_code == 200
    search_request = search_instance.search.call_args[0][1]
    assert search_request.top_k == 20
    assert search_request.threshold == 0.5


@pytest.mark.asyncio
@patch("knowledge.routes.web.search.templates")
async def test_search_page_filters_json_must_be_object(mock_templates):
    """Line 114: non-object JSON should set object-specific error."""
    mock_templates.TemplateResponse.return_value = HTMLResponse("ok", status_code=200)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # collections
            _make_result(scalars_all=[]),  # tenants in _get_common_context
        ]
    )

    response = await search_page(
        request=MagicMock(),
        q="",
        collection_id="",
        collection_ids="",
        top_k=20,
        threshold=0.5,
        distance_type="cosine",
        include_content=True,
        filters_json='["x"]',
        db=db,
        auth_result=_make_auth_context(),
    )

    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] == "Filters must be a JSON object."


@pytest.mark.asyncio
@patch("knowledge.routes.web.search.templates")
async def test_search_page_filters_json_must_be_valid_json(mock_templates):
    """Line 116: invalid JSON should set parsing error."""
    mock_templates.TemplateResponse.return_value = HTMLResponse("ok", status_code=200)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # collections
            _make_result(scalars_all=[]),  # tenants in _get_common_context
        ]
    )

    response = await search_page(
        request=MagicMock(),
        q="",
        collection_id="",
        collection_ids="",
        top_k=20,
        threshold=0.5,
        distance_type="cosine",
        include_content=True,
        filters_json="{bad",
        db=db,
        auth_result=_make_auth_context(),
    )

    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["error"] == "Filters must be valid JSON."


@pytest.mark.asyncio
@patch("knowledge.routes.web.search.SearchService")
@patch("knowledge.routes.web.search.templates")
async def test_search_page_all_collections_ignores_collection_filters(
    mock_templates, mock_search_service
):
    """When all_collections is true, SearchRequest.collection_ids should be None."""
    mock_templates.TemplateResponse.return_value = HTMLResponse("ok", status_code=200)

    search_instance = mock_search_service.return_value
    search_instance.search = AsyncMock(
        return_value=MagicMock(results=[], query="q", total_results=0)
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _make_result(scalars_all=[]),  # collections
            _make_result(scalars_all=[]),  # tenants
        ]
    )

    response = await search_page(
        request=MagicMock(),
        q="q",
        collection_id="legacy-id",
        collection_ids="a,b",
        all_collections=True,
        top_k=20,
        threshold=0.5,
        distance_type="cosine",
        include_content=True,
        filters_json="",
        db=db,
        auth_result=_make_auth_context(),
    )

    assert response.status_code == 200
    search_request = search_instance.search.call_args[0][1]
    assert search_request.collection_ids is None
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["selected_all_collections"] is True


@pytest.mark.asyncio
async def test_search_submit_uses_checkbox_collection_ids_list():
    """Checkbox-selected collection IDs are serialized into collection_ids query param."""
    response = await search_submit(
        request=MagicMock(),
        query="hello",
        collection_ids_list=["id1", "id2", "id1"],
        all_collections="false",
        collection_id="",
        collection_ids="",
        top_k=20,
        threshold=0.5,
        distance_type="cosine",
        include_content="true",
        filters_json="",
        db=AsyncMock(),
        auth_result=_make_auth_context(),
    )
    assert response.status_code == 302
    assert "q=hello" in response.headers["location"]
    assert "collection_ids=id1%2Cid2" in response.headers["location"]


@pytest.mark.asyncio
async def test_search_submit_all_collections_omits_collection_ids():
    """When all_collections is checked, collection_ids should be omitted from redirect."""
    response = await search_submit(
        request=MagicMock(),
        query="hello",
        collection_ids_list=["id1", "id2"],
        all_collections="true",
        collection_id="legacy-id",
        collection_ids="legacy-a,legacy-b",
        top_k=20,
        threshold=0.5,
        distance_type="cosine",
        include_content="true",
        filters_json="",
        db=AsyncMock(),
        auth_result=_make_auth_context(),
    )
    assert response.status_code == 302
    assert "all_collections=true" in response.headers["location"]
    assert "collection_ids=" not in response.headers["location"]
