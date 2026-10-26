# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

from frontend.config import Settings


def test_defaults(monkeypatch) -> None:
    for name in ("APP_NAME", "DEBUG", "DOCS_ENABLED", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.app_name == "GOABONGA"
    assert s.debug is False
    assert s.docs_enabled is False
    assert s.cors_origins == ["*"]
    assert s.cors_credentials is True
    assert s.cors_methods == ["*"]
    assert s.cors_headers == ["*"]


def test_env_override_is_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Custom")
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.test"]')
    monkeypatch.setenv("docs_enabled", "true")
    s = Settings(_env_file=None)
    assert s.app_name == "Custom"
    assert s.cors_origins == ["https://a.test"]
    assert s.docs_enabled is True


def test_env_file_is_read(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=FromFile\nDEBUG=true\n", encoding="utf-8")
    s = Settings(_env_file=env_file)
    assert s.app_name == "FromFile"
    assert s.debug is True
