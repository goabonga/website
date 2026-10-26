# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Settings loading and CORS parsing."""

from pathlib import Path

import pytest
from apt_server.config import Settings, parse_cors

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_defaults() -> None:
    cfg = make_settings()

    assert cfg.app_name == "apt-server"
    assert cfg.log_level == "INFO"
    assert cfg.docs_enabled is False
    assert cfg.all_cors_origins == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example, https://b.example", ["https://a.example", "https://b.example"]),
        ("https://a.example", ["https://a.example"]),
        ("", []),
        (" , ", []),
        (["https://a.example"], ["https://a.example"]),
    ],
)
def test_parse_cors_accepts_strings_and_lists(raw: object, expected: list[str]) -> None:
    assert parse_cors(raw) == expected


def test_parse_cors_keeps_json_arrays_for_pydantic() -> None:
    assert parse_cors('["https://a.example"]') == '["https://a.example"]'


def test_parse_cors_rejects_other_types() -> None:
    with pytest.raises(ValueError):
        parse_cors(42)


def test_cors_origins_merge_frontend_host_and_strip_slashes() -> None:
    cfg = make_settings(
        backend_cors_origins="https://a.example/, https://b.example",
        frontend_host="https://front.example",
    )

    assert cfg.all_cors_origins == [
        "https://a.example",
        "https://b.example",
        "https://front.example",
    ]


def test_cors_origins_accept_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://a.example"]')

    assert make_settings().all_cors_origins == ["https://a.example"]


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "custom")
    monkeypatch.setenv("DOCS_ENABLED", "true")

    cfg = make_settings()

    assert cfg.app_name == "custom"
    assert cfg.docs_enabled is True


def test_env_example_only_lists_known_settings() -> None:
    keys = {
        line.split("=", 1)[0].lower()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    }

    assert keys
    assert keys <= set(Settings.model_fields)
