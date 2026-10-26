# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.main import APP_DIR, DEFAULT_STATIC_DIR, TEMPLATES_DIR, create_app, template_context

SettingsFactory = Callable[..., Settings]


def test_injection_settings_defaults(monkeypatch) -> None:
    for name in ("WELCOME_NAME", "WELCOME_WORDS", "STATIC_DIR", "LEGAL_COMPANY_NAME"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.static_dir == ""
    assert s.auth_url == s.api_url == s.analytics_url == s.oauth2_client_id == ""
    assert s.legal_company_name == "GOABONGA"
    assert s.legal_address == s.legal_host_phone == ""
    assert s.welcome_name == "Chris"
    assert s.welcome_words == "super,cool,awesome,great"
    assert s.social_github == s.social_linkedin == s.social_huggingface == ""


def test_default_static_dir_is_the_web_client_build() -> None:
    assert Path(__file__).resolve().parents[1] == APP_DIR
    assert DEFAULT_STATIC_DIR == APP_DIR / "web" / "dist"


def test_root_serves_the_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>GOABONGA</title>" in response.text


def test_any_path_serves_the_page(client: TestClient) -> None:
    for path in ("/login", "/some/deep/route", "/auth/callback"):
        response = client.get(path)
        assert response.status_code == 200
        assert "<title>GOABONGA</title>" in response.text


def test_settings_are_injected(make_settings: SettingsFactory) -> None:
    client = TestClient(
        create_app(
            make_settings(
                app_name="TESTAPP",
                auth_url="https://auth.test",
                api_url="https://api.test",
                analytics_url="https://ua.test",
                oauth2_client_id="client-123",
                welcome_name="Alice",
                legal_company_name="ACME",
                legal_city="Paris",
                social_github="https://github.test/alice",
            )
        )
    )
    body = client.get("/some/deep/route").text
    assert "<title>TESTAPP</title>" in body
    assert 'authUrl: "https://auth.test"' in body
    assert 'apiUrl: "https://api.test"' in body
    assert 'analyticsUrl: "https://ua.test"' in body
    assert '"client-123"' in body
    assert 'welcomeName: "Alice"' in body
    assert 'companyName: "ACME"' in body
    assert 'city: "Paris"' in body
    assert 'href="https://github.test/alice"' in body


def test_welcome_words_are_rendered(make_settings: SettingsFactory) -> None:
    client = TestClient(create_app(make_settings(welcome_words="alpha,beta,gamma")))
    body = client.get("/").text
    assert '<b class="is-visible">alpha</b><b>beta</b><b>gamma</b>' in body


def test_values_are_html_escaped(make_settings: SettingsFactory) -> None:
    client = TestClient(create_app(make_settings(app_name="<script>x</script>")))
    body = client.get("/").text
    assert "<title>&lt;script&gt;x&lt;/script&gt;</title>" in body


def test_values_in_the_javascript_configuration_are_json(make_settings: SettingsFactory) -> None:
    client = TestClient(
        create_app(
            make_settings(
                legal_company_name="O'Brien & Sons",
                auth_url="https://auth.test/?a=1&b=2",
                legal_city="</script><script>alert(1)",
            )
        )
    )
    body = client.get("/").text
    assert 'companyName: "O\\u0027Brien \\u0026 Sons"' in body
    assert 'authUrl: "https://auth.test/?a=1\\u0026b=2"' in body
    assert "&#39;" not in body.split("window.APP_CONFIG")[1].split("</script>")[0]
    assert "</script><script>alert(1)" not in body


def test_host_phone_is_optional(make_settings: SettingsFactory) -> None:
    without = TestClient(create_app(make_settings())).get("/").text
    with_phone = TestClient(create_app(make_settings(legal_host_phone="+33 1 23"))).get("/").text
    assert " Phone: " not in without
    assert " Phone: +33 1 23<br/>" in with_phone


def test_template_context_covers_every_template_variable() -> None:
    template = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r"{{\s*([a-z_]+)", template)) - {"word"}
    context = template_context(Settings(_env_file=None))
    assert used <= set(context)
    assert set(context) <= used


@pytest.fixture
def build_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index.js").write_text("console.log('hi')", encoding="utf-8")
    return tmp_path


def test_static_files_are_served(make_settings: SettingsFactory, build_dir: Path) -> None:
    client = TestClient(create_app(make_settings(static_dir=str(build_dir))))
    response = client.get("/static/assets/index.js")
    assert response.status_code == 200
    assert response.text == "console.log('hi')"
    assert client.get("/static/assets/missing.js").status_code == 404


def test_static_mount_is_skipped_when_the_directory_is_missing(
    make_settings: SettingsFactory, tmp_path: Path
) -> None:
    client = TestClient(create_app(make_settings(static_dir=str(tmp_path / "absent"))))
    response = client.get("/static/assets/index.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_health_is_not_shadowed_by_the_catch_all(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "healthy"}


def test_unmatched_documentation_paths_fall_back_to_the_page(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_documentation_paths_win_when_enabled(make_settings: SettingsFactory) -> None:
    client = TestClient(create_app(make_settings(docs_enabled=True)))
    assert client.get("/openapi.json").headers["content-type"].startswith("application/json")
