# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Health endpoint, static files and optional Swagger UI."""

import importlib

import apt_server.main as main_module
import pytest
from apt_server.config import settings
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_hidden_from_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/health" not in schema["paths"]


def test_package_exposes_version() -> None:
    import apt_server

    assert apt_server.__version__ == "0.0.0"


def test_static_favicon_is_served(client: TestClient) -> None:
    response = client.get("/static/favicon.ico")

    assert response.status_code == 200
    assert len(response.content) > 0


def test_docs_are_disabled_by_default(client: TestClient) -> None:
    assert settings.docs_enabled is False
    assert client.get("/docs").status_code == 404


@pytest.fixture
def docs_app(monkeypatch: pytest.MonkeyPatch):
    """Reload the application module with Swagger UI enabled."""
    monkeypatch.setattr(settings, "docs_enabled", True)
    importlib.reload(main_module)
    yield main_module.app
    monkeypatch.undo()
    importlib.reload(main_module)


def test_docs_use_local_swagger_assets_when_enabled(docs_app) -> None:
    with TestClient(docs_app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert "/static/swagger-ui-bundle.js" in response.text
    assert "/static/swagger-ui.css" in response.text


def test_swagger_oauth2_redirect_page_is_served(docs_app) -> None:
    with TestClient(docs_app) as client:
        response = client.get("/docs/oauth2-redirect")

    assert response.status_code == 200
