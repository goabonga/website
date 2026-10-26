# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from collections.abc import Callable

from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.main import create_app
from frontend.security_txt import FIELDS, generate_security_txt

SettingsFactory = Callable[..., Settings]


def test_security_settings_default_to_empty(monkeypatch) -> None:
    for _, attr in FIELDS:
        monkeypatch.delenv(attr.upper(), raising=False)
    s = Settings(_env_file=None)
    assert all(getattr(s, attr) == "" for _, attr in FIELDS)


def test_empty_settings_give_empty_content(make_settings: SettingsFactory) -> None:
    assert generate_security_txt(make_settings()) == ""


def test_required_fields(make_settings: SettingsFactory) -> None:
    cfg = make_settings(security_contact="mailto:sec@example.test", security_expires="2030-01-01")
    assert generate_security_txt(cfg) == ("Contact: mailto:sec@example.test\nExpires: 2030-01-01")


def test_all_fields_are_written_in_order(make_settings: SettingsFactory) -> None:
    values = {attr: f"v-{attr}" for _, attr in FIELDS}
    lines = generate_security_txt(make_settings(**values)).splitlines()
    assert lines == [f"{name}: v-{attr}" for name, attr in FIELDS]
    assert [line.split(":")[0] for line in lines] == [
        "Contact",
        "Expires",
        "Encryption",
        "Acknowledgments",
        "Preferred-Languages",
        "Canonical",
        "Policy",
        "Hiring",
        "CSAF",
    ]


def test_empty_fields_are_omitted(make_settings: SettingsFactory) -> None:
    cfg = make_settings(
        security_contact="mailto:sec@example.test", security_policy="https://p.test"
    )
    assert generate_security_txt(cfg) == "Contact: mailto:sec@example.test\nPolicy: https://p.test"


def test_endpoint_returns_plain_text(make_settings: SettingsFactory) -> None:
    client = TestClient(create_app(make_settings(security_contact="mailto:sec@example.test")))
    response = client.get("/.well-known/security.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Contact: mailto:sec@example.test"


def test_endpoint_is_empty_when_unconfigured(client: TestClient) -> None:
    response = client.get("/.well-known/security.txt")
    assert response.status_code == 200
    assert response.text == ""


def test_endpoint_is_not_served_by_the_catch_all(client: TestClient) -> None:
    response = client.get("/.well-known/security.txt")
    assert not response.headers["content-type"].startswith("text/html")


def test_endpoint_is_hidden_from_openapi(make_settings: SettingsFactory) -> None:
    client = TestClient(create_app(make_settings(docs_enabled=True)))
    assert "/.well-known/security.txt" not in client.get("/openapi.json").json()["paths"]
