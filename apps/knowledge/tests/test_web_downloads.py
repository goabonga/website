# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for web downloads routes (knowledge/routes/web/downloads.py)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.responses import HTMLResponse

from knowledge.database import get_db
from knowledge.internal import internal_app
from knowledge.models.enums import ReleaseStatus


def _html_response(status_code=200):
    """Return a real HTMLResponse for template mock return values."""
    return HTMLResponse(content="<html>ok</html>", status_code=status_code)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(scalar_one_or_none=None, scalar=0, scalars_all=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    return result


def _make_mock_release(**overrides):
    release = MagicMock()
    release.id = overrides.get("id", uuid4())
    release.version = overrides.get("version", "1.0.0")
    release.status = overrides.get("status", ReleaseStatus.PUBLISHED)
    release.published_at = overrides.get("published_at", "2024-01-01")
    release.assets = overrides.get("assets", [])
    return release


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
async def web_client(mock_db):
    async def override_get_db():
        yield mock_db

    internal_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=internal_app),
        base_url="http://test",
    ) as ac:
        yield ac

    internal_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# mcp_downloads_page
# ---------------------------------------------------------------------------


@patch("knowledge.routes.web.downloads.templates")
async def test_mcp_downloads_with_releases(mock_templates, web_client, mock_db):
    """Test /mcp returns releases when available."""
    release1 = _make_mock_release(version="1.1.0")
    release2 = _make_mock_release(version="1.0.0")

    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[release1, release2]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/mcp")
    assert response.status_code == 200
    call_args = mock_templates.TemplateResponse.call_args
    assert call_args[0][1] == "pages/mcp_downloads.html"
    ctx = call_args[0][2]
    assert len(ctx["releases"]) == 2
    assert ctx["latest_release"] is release1


@patch("knowledge.routes.web.downloads.templates")
async def test_mcp_downloads_no_releases(mock_templates, web_client, mock_db):
    """Test /mcp with no releases."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/mcp")
    assert response.status_code == 200
    ctx = mock_templates.TemplateResponse.call_args[0][2]
    assert ctx["releases"] == []
    assert ctx["latest_release"] is None


@patch("knowledge.routes.web.downloads.templates")
async def test_mcp_downloads_alternate_path(mock_templates, web_client, mock_db):
    """Test /mcp/downloads also works."""
    mock_db.execute = AsyncMock(
        return_value=_make_result(scalars_all=[]),
    )
    mock_templates.TemplateResponse.return_value = _html_response()

    response = await web_client.get("/mcp/downloads")
    assert response.status_code == 200
    mock_templates.TemplateResponse.assert_called_once()
