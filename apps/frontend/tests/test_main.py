# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from collections.abc import Callable

from fastapi.testclient import TestClient
from frontend import __version__
from frontend.config import Settings
from frontend.main import app, create_app


def test_version() -> None:
    assert __version__ == "0.0.0"


def test_module_level_app_is_built() -> None:
    assert app.title


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_is_hidden_from_openapi(make_settings: Callable[..., Settings]) -> None:
    api = create_app(make_settings(docs_enabled=True))
    schema = TestClient(api).get("/openapi.json").json()
    assert "/health" not in schema["paths"]


def test_title_and_version_follow_settings(make_settings: Callable[..., Settings]) -> None:
    api = create_app(make_settings(app_name="TESTAPP"))
    assert api.title == "TESTAPP"
    assert api.version == __version__


def test_docs_disabled_by_default(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_docs_can_be_enabled(make_settings: Callable[..., Settings]) -> None:
    client = TestClient(create_app(make_settings(docs_enabled=True)))
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_cors_allows_any_origin_by_default(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://example.org"})
    assert response.headers["access-control-allow-origin"] in {"*", "https://example.org"}


def test_cors_origins_are_restricted_by_settings(make_settings: Callable[..., Settings]) -> None:
    client = TestClient(create_app(make_settings(cors_origins=["https://a.test"])))
    allowed = client.get("/health", headers={"Origin": "https://a.test"})
    denied = client.get("/health", headers={"Origin": "https://b.test"})
    assert allowed.headers["access-control-allow-origin"] == "https://a.test"
    assert "access-control-allow-origin" not in denied.headers
